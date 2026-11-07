from .schemas import PatientInput, Lab, TrialInput
from .db import Patient, Trial


def seed(session):
    if not session.query(Patient).first():
        patients = [
            PatientInput(code="DEMO-001", age=54, sex="female", conditions=["T2DM", "HTN"],
                         medications=["Metformin"], labs={"HbA1c": Lab(value=8.2, unit="%"), "eGFR": Lab(value=72, unit="mL/min/1.73m2")}, synthetic=True),
            PatientInput(code="DEMO-002", age=67, sex="male", conditions=["NSCLC"], synthetic=True),
            PatientInput(code="DEMO-003", age=42, sex="female", conditions=["Heart failure"], synthetic=True),
        ]
        session.add_all([Patient(data=p.model_dump()) for p in patients])
    if not session.query(Trial).first():
        specs = [
            ("DEMO-DM-01", "Improving glycemic outcomes in type 2 diabetes", ["Type 2 diabetes"], "Phase 3", 18, 75,
             "Inclusion Criteria:\nType 2 diabetes\nHbA1c >= 7%\neGFR >= 45 mL/min/1.73m2\nExclusion Criteria:\nChronic kidney disease"),
            ("DEMO-DM-02", "Lifestyle and metabolic health in adults with diabetes", ["Type 2 diabetes", "Hypertension"], "Phase 2", 30, 70,
             "Inclusion Criteria:\nType 2 diabetes\nHbA1c >= 6.5%\nExclusion Criteria:\nMyocardial infarction within the last six months"),
            ("DEMO-DM-03", "Renal outcomes in diabetes and chronic kidney disease", ["Type 2 diabetes", "Chronic kidney disease"], "Phase 3", 18, 80,
             "Inclusion Criteria:\nType 2 diabetes\neGFR < 45 mL/min/1.73m2"),
            ("DEMO-LC-01", "Targeted research in non-small cell lung cancer", ["NSCLC"], "Phase 2", 18, None,
             "Inclusion Criteria:\nNSCLC\nConfirmed stage IV disease\nExclusion Criteria:\nTreatment within the previous 30 days"),
            ("DEMO-HF-01", "Functional outcomes in chronic heart failure", ["Heart failure"], "Phase 3", 21, 85,
             "Inclusion Criteria:\nHeart failure\neGFR >= 30 mL/min/1.73m2\nExclusion Criteria:\nMyocardial infarction"),
            ("DEMO-HT-01", "Remote monitoring for hypertension management", ["Hypertension"], "Not applicable", 18, 80,
             "Inclusion Criteria:\nHypertension\nAbility to provide informed consent"),
        ]
        for id, title, conditions, phase, low, high, eligibility in specs:
            trial = TrialInput(id=id, title=title, conditions=conditions, phase=phase, min_age=low, max_age=high,
                status="RECRUITING", sponsor="Synthetic Research Collaborative", locations=["Demo research center"],
                summary="Fictional study for software demonstration. Not a real enrollment opportunity.",
                eligibility=eligibility, source="Synthetic demonstration dataset", synthetic=True)
            session.add(Trial(id=id, data=trial.model_dump()))
    session.commit()
