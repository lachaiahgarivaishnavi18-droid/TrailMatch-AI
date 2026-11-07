import operator
from .nlp import normalize
from .schemas import Criterion, Evidence, MatchResult, PatientInput, Candidate

COMPARATORS = {"gte": operator.ge, "lte": operator.le, "gt": operator.gt, "lt": operator.lt, "eq": operator.eq}


def canonical_unit(unit):
    return (unit or "").lower().replace(" ", "").replace("²", "2").replace("percent", "%")


def evaluate(patient: PatientInput, criterion: Criterion) -> Evidence:
    value, predicate, explanation = None, None, "Criterion requires human interpretation."
    if not criterion.review_required and criterion.operator != "review":
        if criterion.attribute in ["age", "sex"]:
            value = getattr(patient, criterion.attribute)
            if value is not None and value != "unknown":
                predicate = COMPARATORS[criterion.operator](value, criterion.value)
                explanation = "Compared with structured patient field."
        elif criterion.attribute in ["conditions", "medications"]:
            value = [normalize(x) for x in getattr(patient, criterion.attribute)]
            if normalize(str(criterion.value)) in value:
                predicate = True
            elif patient.history_complete:
                predicate = False
            explanation = "Compared with normalized history; absence is unknown unless history is confirmed complete."
        else:
            labs = {normalize(k): v for k, v in patient.labs.items()}
            lab = labs.get(criterion.attribute)
            if lab:
                value = f"{lab.value} {lab.unit}"
                if canonical_unit(lab.unit) == canonical_unit(criterion.unit):
                    predicate = COMPARATORS[criterion.operator](lab.value, criterion.value)
                    explanation = "Compared numeric value using matching units."
                else:
                    explanation = "Units differ or are unspecified; no automatic conversion was applied."
    if predicate is None:
        status = "unknown"
        if value is None and not criterion.review_required:
            explanation = "Required patient data is missing."
    else:
        satisfied = predicate if criterion.kind == "inclusion" else not predicate
        status = "met" if satisfied else "not_met"
        if criterion.kind == "exclusion":
            explanation += " Exclusion is met when the disqualifying condition is absent."
    return Evidence(criterion=criterion, status=status, patient_value=str(value) if value is not None else "Not provided", explanation=explanation)


def match_candidate(patient: PatientInput, candidate: Candidate, criteria: list[Criterion]) -> MatchResult:
    evidence = [evaluate(patient, c) for c in criteria]
    met = sum(e.status == "met" for e in evidence)
    conflicts = sum(e.status == "not_met" for e in evidence)
    unknown = sum(e.status == "unknown" for e in evidence)
    active = candidate.trial.status in ["RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"]
    disposition = "constraint_conflict" if conflicts else "needs_review" if unknown or not active else "potential_match"
    score = round(100 * (.45 * candidate.similarity + .55 * met / max(len(evidence), 1)), 1)
    return MatchResult(trial=candidate.trial, similarity=candidate.similarity, score=score, disposition=disposition,
                       evidence=evidence, summary=f"{met} criteria met, {conflicts} conflicts, {unknown} unknown. "
                       + ("Recruitment status requires review. " if not active else "")
                       + "Research prioritization only; qualified staff must confirm all eligibility requirements.")
