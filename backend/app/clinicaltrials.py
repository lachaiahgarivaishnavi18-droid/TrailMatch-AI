from datetime import datetime, timezone
import re
import httpx
from .schemas import TrialInput


def age_years(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s+(Years?|Months?|Weeks?|Days?)", value or "", re.I)
    if not match:
        return None
    return float(match[1]) / {"year": 1, "month": 12, "week": 52.1775, "day": 365.25}[match[2].lower().rstrip("s")]


def fetch_trials(condition: str, limit: int) -> list[TrialInput]:
    # Fixed upstream host; no arbitrary URL fetching and no patient records transmitted.
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.get("https://clinicaltrials.gov/api/v2/studies", params={"query.cond": condition, "pageSize": limit, "format": "json"})
        response.raise_for_status()
    trials = []
    for study in response.json().get("studies", []):
        p = study.get("protocolSection", {})
        identity, status, design = p.get("identificationModule", {}), p.get("statusModule", {}), p.get("designModule", {})
        eligibility = p.get("eligibilityModule", {})
        nct = identity.get("nctId", "")
        if not re.fullmatch(r"NCT\d{8}", nct):
            continue
        trials.append(TrialInput(id=nct, title=identity.get("briefTitle", nct),
            conditions=p.get("conditionsModule", {}).get("conditions", []),
            interventions=[i.get("name", "") for i in p.get("armsInterventionsModule", {}).get("interventions", [])],
            sponsor=p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "Not reported"),
            phase=", ".join(design.get("phases", [])) or "Not applicable", status=status.get("overallStatus", "UNKNOWN"),
            locations=[", ".join(str(l[k]) for k in ["facility", "city", "country"] if l.get(k)) for l in p.get("contactsLocationsModule", {}).get("locations", [])],
            summary=p.get("descriptionModule", {}).get("briefSummary", ""), eligibility=eligibility.get("eligibilityCriteria", ""),
            min_age=age_years(eligibility.get("minimumAge")), max_age=age_years(eligibility.get("maximumAge")), sex=eligibility.get("sex", "ALL"),
            source="ClinicalTrials.gov", source_url=f"https://clinicaltrials.gov/study/{nct}", retrieved_at=datetime.now(timezone.utc).isoformat()))
    return trials
