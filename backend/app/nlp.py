"""Conservative terminology normalization and explicit constraint extraction."""
import re
from .schemas import Criterion, PatientInput, ProfileOutput, TrialInput

ALIASES = {
    "type 2 diabetes": ["t2dm", "t2d", "type ii diabetes", "diabetes mellitus type 2"],
    "non small cell lung cancer": ["nsclc", "non-small cell lung cancer", "non-small-cell lung cancer"],
    "hypertension": ["htn", "high blood pressure"],
    "chronic kidney disease": ["ckd"],
    "heart failure": ["chf", "congestive heart failure"],
    "myocardial infarction": ["heart attack", "mi"],
    "metformin": ["glucophage"],
    "hba1c": ["a1c", "glycated hemoglobin", "haemoglobin a1c"],
    "egfr": ["estimated glomerular filtration rate"],
}


def normalize(text: str) -> str:
    text = text.lower().strip()
    for concept, aliases in ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            text = re.sub(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", concept, text)
    return text


def understand(patient: PatientInput) -> ProfileOutput:
    missing = []
    if patient.age is None:
        missing.append("Age")
    if patient.sex == "unknown":
        missing.append("Sex")
    if not patient.conditions:
        missing.append("Structured condition history")
    if not patient.history_complete:
        missing.append("Confirmed complete condition and medication history")
    entities, provenance = [], []
    for attribute in ["conditions", "medications", "allergies"]:
        for value in getattr(patient, attribute):
            entities.append({"type": attribute, "text": value, "normalized": normalize(value), "confirmed": True})
            provenance.append({"field": attribute, "source": "structured patient input", "original": value})
    # Notes produce suggestions only: negation, timing and subject cannot be reliably resolved here.
    note = normalize(patient.notes)
    for concept in ALIASES:
        if re.search(r"(?<!\w)" + re.escape(concept) + r"(?!\w)", note):
            entities.append({"type": "note_mention", "text": concept, "normalized": concept, "confirmed": False})
    if patient.notes:
        missing.append("Human confirmation of clinical-note mentions and temporal context")
        provenance.append({"field": "notes", "source": "uploaded text or manually entered note", "original": patient.notes})
    for key, lab in patient.labs.items():
        provenance.append({"field": f"labs.{key}", "source": "structured patient input", "original": lab.model_dump()})
    return ProfileOutput(patient=patient, normalized_conditions=[normalize(x) for x in patient.conditions],
                         normalized_medications=[normalize(x) for x in patient.medications],
                         entities=entities, missing_information=missing, provenance=provenance)


OPS = {">=": "gte", "≤": "lte", ">": "gt", "<": "lt", "<=": "lte", "≥": "gte",
       "greater than or equal to": "gte", "at least": "gte", "no less than": "gte",
       "less than or equal to": "lte", "at most": "lte", "no more than": "lte",
       "greater than": "gt", "less than": "lt"}
OP_PATTERN = "|".join(re.escape(x) for x in sorted(OPS, key=len, reverse=True))


def extract(trial: TrialInput) -> list[Criterion]:
    out = []
    for attribute, op, value, unit in [("age", "gte", trial.min_age, "years"), ("age", "lte", trial.max_age, "years")]:
        if value is not None:
            out.append(Criterion(attribute=attribute, operator=op, value=value, unit=unit,
                                 original=f"Registry structured field: {attribute} {op} {value} {unit}"))
    if trial.sex.upper() in ["FEMALE", "MALE"]:
        out.append(Criterion(attribute="sex", operator="eq", value=trial.sex.lower(), original=f"Registry sex: {trial.sex}"))
    kind = None
    for raw in trial.eligibility.splitlines():
        line = raw.strip().lstrip("-*• ")
        if not line:
            continue
        if re.fullmatch(r"(?:key )?inclusion criteria:?", line, re.I):
            kind = "inclusion"
            continue
        if re.fullmatch(r"(?:key )?exclusion criteria:?", line, re.I):
            kind = "exclusion"
            continue
        text = normalize(line)
        parsed = []
        # Complex logic and temporal constraints must never be reduced to simple keyword checks.
        complex_text = re.search(r"\b(or|unless|except|within|previous|past|last|stage|not|no|without)\b", text)
        if not complex_text:
            for attr in ["age", "hba1c", "egfr", "bmi"]:
                subject = r"(?:age|aged|years old|participants must be)" if attr == "age" else re.escape(attr)
                pattern = subject + r"(?:\s+(?:level|of|is|must be))?\s*(" + OP_PATTERN + r")\s*(\d+(?:\.\d+)?)\s*([^;,\n]*)"
                for m in re.finditer(pattern, text):
                    tail = m[3].strip()
                    unit = "years" if attr == "age" else ("%" if tail.startswith("%") else "mL/min/1.73m2" if re.match(r"ml/min/1\.73\s*m(?:2|²)", tail) else "kg/m2" if re.match(r"kg/m(?:2|²)", tail) else None)
                    allowed_tail = {"age": r"(?:years?(?: old)?)?\.?", "hba1c": r"%\.?", "egfr": r"ml/min/1\.73\s*m(?:2|²)\.?", "bmi": r"kg/m(?:2|²)\.?"}[attr]
                    # Recognizing one threshold must not silently discard trailing protocol text.
                    incomplete = not re.fullmatch(allowed_tail, tail) or m.start() != 0
                    parsed.append(Criterion(kind=kind or "inclusion", attribute=attr, operator=OPS[m[1]], value=float(m[2]), unit=unit,
                                            original=line, review_required=unit is None or incomplete))
            # Only short single-concept declarations are accepted as explicit categorical rules.
            categorical = re.fullmatch(r"(?:diagnosis of |confirmed |current use of |taking |history of )?([\w -]+)\.?", text)
            if categorical and not parsed:
                concept = categorical[1].rstrip(".").strip()
                if concept in ALIASES:
                    attr = "medications" if concept == "metformin" else "conditions"
                    parsed.append(Criterion(kind=kind or "inclusion", attribute=attr, operator="contains", value=concept, original=line))
        if not parsed:
            parsed = [Criterion(kind=kind or "inclusion", attribute="unstructured", operator="review", original=line, review_required=True)]
        # If a line combines clauses, require review even when one numeric clause was recognized.
        if parsed and re.search(r"\b(and|with)\b", text):
            parsed.append(Criterion(kind=kind or "inclusion", attribute="compound_clause", operator="review", original=line, review_required=True))
        if kind is None:
            for criterion in parsed:
                criterion.review_required = True
                criterion.explicit = False
        out.extend(parsed)
    if not trial.eligibility.strip():
        out.append(Criterion(attribute="eligibility", operator="review", original="Full eligibility text unavailable", review_required=True))
    return out
