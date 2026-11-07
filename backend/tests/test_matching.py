import pytest
from app.schemas import PatientInput, Criterion, Lab, TrialInput, Candidate
from app.nlp import normalize, understand, extract
from app.evaluation import evaluate, match_candidate
from app.agents import run_matching
from app.clinicaltrials import age_years


def test_synonyms_and_note_mentions_do_not_become_diagnoses():
    p = PatientInput(code="T", conditions=["T2DM"], notes="No CKD. Mother had NSCLC.")
    profile = understand(p)
    assert normalize("T2DM and high blood pressure") == "type 2 diabetes and hypertension"
    assert profile.normalized_conditions == ["type 2 diabetes"]
    assert all(not x["confirmed"] for x in profile.entities if x["type"] == "note_mention")


@pytest.mark.parametrize("age,expected", [(17,"not_met"),(18,"met"),(19,"met"),(None,"unknown")])
def test_age_threshold_boundaries(age, expected):
    c = Criterion(attribute="age", operator="gte", value=18, original="Age >= 18")
    assert evaluate(PatientInput(code="T", age=age), c).status == expected


def test_exclusion_unknown_is_never_passed():
    c = Criterion(kind="exclusion", attribute="conditions", operator="contains", value="chronic kidney disease", original="CKD")
    assert evaluate(PatientInput(code="T"), c).status == "unknown"
    assert evaluate(PatientInput(code="T", conditions=["CKD"]), c).status == "not_met"
    assert evaluate(PatientInput(code="T", history_complete=True), c).status == "met"


def test_lab_units_and_missing_values():
    c = Criterion(attribute="hba1c", operator="gte", value=7, unit="%", original="HbA1c >= 7%")
    assert evaluate(PatientInput(code="T", labs={"A1c": Lab(value=8.2,unit="%")}), c).status == "met"
    assert evaluate(PatientInput(code="T", labs={"A1c": Lab(value=63,unit="mmol/mol")}), c).status == "unknown"
    assert evaluate(PatientInput(code="T"), c).status == "unknown"


def test_criteria_parser_preserves_temporal_negation_compound_and_unknown():
    t=TrialInput(id="T", title="Trial", eligibility="Inclusion Criteria:\nHbA1c >= 7%\nAge >= 18 and consent\nExclusion Criteria:\nMI within the last six months\nNo prior surgery\nCKD")
    c=extract(t)
    assert c[0].attribute == "hba1c" and c[0].value == 7
    assert any(x.attribute == "compound_clause" and x.review_required for x in c)
    assert any(x.original == "MI within the last six months" and x.review_required for x in c)
    assert any(x.original == "No prior surgery" and x.review_required for x in c)
    assert c[-1].value == "chronic kidney disease" and c[-1].kind == "exclusion"


def test_missing_eligibility_and_closed_recruitment_require_review():
    trial=TrialInput(id="T",title="Diabetes",status="COMPLETED",min_age=18)
    r=match_candidate(PatientInput(code="T",age=40),Candidate(trial=trial,similarity=.99),extract(trial))
    assert r.disposition == "needs_review"
    assert any(e.status == "unknown" for e in r.evidence)


def test_real_langgraph_execution_and_conflict_grouping():
    p=PatientInput(code="T",age=55,conditions=["T2DM"],labs={"HbA1c":Lab(value=8,unit="%")})
    trials=[TrialInput(id="good",title="Type 2 diabetes trial",conditions=["Type 2 diabetes"],min_age=18,status="RECRUITING",eligibility="Inclusion Criteria:\nHbA1c >= 7%"),TrialInput(id="bad",title="Type 2 diabetes trial",conditions=["Type 2 diabetes"],max_age=40,status="RECRUITING",eligibility="Inclusion Criteria:\nHbA1c >= 7%")]
    r=run_matching(p,trials,10)
    assert len(r["logs"]) == 5
    assert r["results"][0]["trial"]["id"] == "good"
    assert r["results"][0]["disposition"] == "potential_match"
    assert r["results"][1]["disposition"] == "constraint_conflict"


def test_registry_age_units():
    assert age_years("18 Years") == 18
    assert age_years("6 Months") == .5
    assert age_years("N/A") is None


def test_numeric_extraction_does_not_discard_residual_protocol_text():
    for line in ["HbA1c >= 7% despite stable therapy", "HbA1c >= 7% - additional restrictions apply", "Investigators require HbA1c >= 7%"]:
        criteria=extract(TrialInput(id="T",title="T",eligibility="Inclusion Criteria:\n"+line))
        assert all(c.review_required for c in criteria)


def test_unlabeled_criteria_require_review_and_key_exclusions_are_recognized():
    c=extract(TrialInput(id="T",title="T",eligibility="HbA1c >= 7%\nKey Exclusion Criteria:\nCKD"))
    assert c[0].review_required and not c[0].explicit
    assert c[1].kind == "exclusion" and not c[1].review_required
