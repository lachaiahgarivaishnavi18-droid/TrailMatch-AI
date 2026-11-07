import csv
import io
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DBSession
from pydantic import ValidationError
import httpx
from .db import Base, engine, get_session, Session, Patient, Trial, MatchRun
from .schemas import PatientInput, TrialInput, MatchRequest, ImportRequest
from .seed import seed
from .agents import run_matching
from .nlp import understand, extract
from .clinicaltrials import fetch_trials
from .providers import suggest_criteria


@asynccontextmanager
async def lifespan(app):
    if os.getenv("VERCEL") and engine.url.get_backend_name() == "sqlite":
        raise RuntimeError("Vercel requires a durable PostgreSQL DATABASE_URL. Local SQLite is unsupported on this deployment.")
    # Multiple serverless instances may cold-start together. Serialize PostgreSQL
    # schema/seed initialization without exporting or copying any local records.
    with engine.begin() as connection:
        if engine.url.get_backend_name() == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(746321901)"))
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            seed(session)
    yield


app = FastAPI(title="TrialMatch AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"])


def require(session, model, id):
    item = session.get(model, id)
    if item is None:
        raise HTTPException(404, "Record not found")
    return item


def timestamp(value):
    # SQLite strips offsets from DateTime columns; stored values are always UTC.
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def record(row):
    result = {**row.data, "id": row.id, "created_at": timestamp(row.created_at)}
    if isinstance(row, MatchRun):
        result["patient_id"] = row.patient_id
    return result


@app.get("/api/health")
def health():
    return {"status": "ok", "embedding_provider": os.getenv("EMBEDDING_PROVIDER", "local"), "llm_provider": os.getenv("LLM_PROVIDER", "none")}


@app.get("/api/patients")
def patients(session: DBSession = Depends(get_session)):
    return [record(p) for p in session.scalars(select(Patient).order_by(Patient.created_at.desc()))]


@app.post("/api/patients", status_code=201)
def create_patient(data: PatientInput, session: DBSession = Depends(get_session)):
    row = Patient(data=data.model_dump())
    session.add(row)
    session.commit()
    return record(row)


@app.put("/api/patients/{id}")
def update_patient(id: str, data: PatientInput, session: DBSession = Depends(get_session)):
    row = require(session, Patient, id)
    row.data = data.model_dump()
    session.commit()
    return record(row)


@app.delete("/api/patients/{id}", status_code=204)
def delete_patient(id: str, session: DBSession = Depends(get_session)):
    row = require(session, Patient, id)
    for run in session.scalars(select(MatchRun).where(MatchRun.patient_id == id)):
        session.delete(run)
    session.delete(row)
    session.commit()


@app.get("/api/patients/{id}/profile")
def profile(id: str, session: DBSession = Depends(get_session)):
    return understand(PatientInput.model_validate(require(session, Patient, id).data))


@app.post("/api/patients/import-csv")
async def import_csv(file: UploadFile = File(...), session: DBSession = Depends(get_session)):
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "CSV must be under 2 MB")
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        parsed = []
        for index, row in enumerate(reader, start=2):
            if index > 501:
                raise ValueError("Maximum 500 patient rows per upload")
            parsed.append(PatientInput(code=row.get("code", ""), age=int(row["age"]) if row.get("age") else None,
                sex=row.get("sex") or "unknown", conditions=[x.strip() for x in row.get("conditions", "").split(";") if x.strip()],
                medications=[x.strip() for x in row.get("medications", "").split(";") if x.strip()],
                notes=row.get("notes", ""), labs=json.loads(row.get("labs") or "{}"), synthetic=row.get("synthetic", "").lower() == "true"))
        if not parsed:
            raise ValueError("CSV contains no patient records")
    except (ValueError, UnicodeDecodeError, ValidationError) as error:
        raise HTTPException(422, f"CSV import rejected; no records saved: {error}")
    session.add_all([Patient(data=p.model_dump()) for p in parsed])
    session.commit()
    return {"imported": len(parsed)}


@app.post("/api/patients/{id}/document")
async def upload_document(id: str, file: UploadFile = File(...), session: DBSession = Depends(get_session)):
    row = require(session, Patient, id)
    content = await file.read(20001)
    if len(content) > 20000:
        raise HTTPException(413, "Plain-text clinical note must be under 20 KB")
    try:
        text = content.decode("utf-8")
        if "\x00" in text:
            raise ValueError("Binary content")
        data = PatientInput.model_validate({**row.data, "notes": text})
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(422, "Upload a UTF-8 plain-text note")
    row.data = data.model_dump()
    session.commit()
    return understand(data)


@app.get("/api/trials")
def trials(q: str = "", status: str = "", session: DBSession = Depends(get_session)):
    rows = [record(t) for t in session.scalars(select(Trial))]
    return [t for t in rows if q.lower() in " ".join([t["title"], *t["conditions"], t["id"]]).lower() and (not status or t["status"] == status)]


@app.post("/api/trials", status_code=201)
def save_trial(data: TrialInput, session: DBSession = Depends(get_session)):
    existing = session.get(Trial, data.id)
    if existing:
        existing.data = data.model_dump()
    else:
        session.add(Trial(id=data.id, data=data.model_dump()))
    session.commit()
    return data


@app.post("/api/trials/import")
def import_trials(request: ImportRequest, session: DBSession = Depends(get_session)):
    try:
        incoming = fetch_trials(request.condition, request.limit)
    except (httpx.HTTPError, ValueError, KeyError):
        return {"imported": 0, "fallback": True, "message": "ClinicalTrials.gov unavailable. Existing local trials remain searchable; no registry records were fabricated."}
    for trial in incoming:
        row = session.get(Trial, trial.id)
        if row:
            row.data = trial.model_dump()
        else:
            session.add(Trial(id=trial.id, data=trial.model_dump()))
    session.commit()
    return {"imported": len(incoming), "fallback": False, "message": f"Stored {len(incoming)} registry records (deduplicated by trial ID)."}


@app.get("/api/trials/{id}/criteria")
def criteria(id: str, session: DBSession = Depends(get_session)):
    return extract(TrialInput.model_validate(require(session, Trial, id).data))


@app.post("/api/trials/{id}/suggest-criteria")
def suggestions(id: str, session: DBSession = Depends(get_session)):
    trial = require(session, Trial, id)
    try:
        return suggest_criteria(trial.data["eligibility"])
    except ValueError as error:
        raise HTTPException(422, str(error))
    except httpx.HTTPError:
        raise HTTPException(502, "Configured LLM provider unavailable")


@app.post("/api/matches", status_code=201)
def matching(request: MatchRequest, session: DBSession = Depends(get_session)):
    patient = PatientInput.model_validate(require(session, Patient, request.patient_id).data)
    trials = [TrialInput.model_validate(t.data) for t in session.scalars(select(Trial))]
    try:
        result = run_matching(patient, trials, request.limit)
    except (ImportError, OSError, ValueError) as error:
        raise HTTPException(503, f"Matching provider unavailable: {error}")
    row = MatchRun(patient_id=request.patient_id, data=result)
    session.add(row)
    session.commit()
    return record(row)


@app.get("/api/runs")
def runs(session: DBSession = Depends(get_session)):
    return [{"id": r.id, "patient_id": r.patient_id, "patient_code": r.data["profile"]["patient"]["code"],
             "created_at": timestamp(r.created_at), "result_count": len(r.data["results"])}
            for r in session.scalars(select(MatchRun).order_by(MatchRun.created_at.desc()))]


@app.get("/api/runs/{id}")
def run(id: str, session: DBSession = Depends(get_session)):
    return record(require(session, MatchRun, id))


@app.get("/api/runs/{id}/export")
def export(id: str, format: str = "json", session: DBSession = Depends(get_session)):
    data = record(require(session, MatchRun, id))
    if format == "json":
        return Response(json.dumps(data, indent=2), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="trialmatch-{id}.json"'})
    if format != "csv":
        raise HTTPException(422, "Supported export formats: json, csv")
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["trial_id", "title", "ranking_score", "disposition", "criterion", "kind", "status", "patient_value", "explanation"])
    def safe(value):
        text = str(value)
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
    for result in data["results"]:
        for evidence in result["evidence"]:
            writer.writerow([safe(v) for v in [result["trial"]["id"], result["trial"]["title"], result["score"], result["disposition"], evidence["criterion"]["original"], evidence["criterion"]["kind"], evidence["status"], evidence["patient_value"], evidence["explanation"]]])
    return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="trialmatch-{id}.csv"'})


@app.get("/api/analytics")
def analytics(session: DBSession = Depends(get_session)):
    patients = list(session.scalars(select(Patient)))
    trials = list(session.scalars(select(Trial)))
    runs = list(session.scalars(select(MatchRun)))
    dispositions = {"potential_match": 0, "needs_review": 0, "constraint_conflict": 0}
    for run in runs:
        for result in run.data["results"]:
            dispositions[result["disposition"]] += 1
    return {"patients": len(patients), "trials": len(trials), "runs": len(runs), "dispositions": dispositions,
            "synthetic_trials": sum(t.data.get("synthetic", False) for t in trials),
            "recruiting": sum(t.data["status"] == "RECRUITING" for t in trials)}


# Optional built frontend served from same origin; API routes above retain priority.
dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.exists():
    class SPAFiles(StaticFiles):
        async def get_response(self, path, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as error:
                if error.status_code == 404 and not path.startswith("api/") and "." not in path.rsplit("/", 1)[-1]:
                    return await super().get_response("index.html", scope)
                raise
    app.mount("/", SPAFiles(directory=dist, html=True), name="frontend")
