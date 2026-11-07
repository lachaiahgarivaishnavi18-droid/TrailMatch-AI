from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Lab(BaseModel):
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=40)


class PatientInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=80)
    age: int | None = Field(default=None, ge=0, le=120)
    sex: Literal["female", "male", "unknown"] = "unknown"
    conditions: list[str] = Field(default_factory=list, max_length=50)
    medications: list[str] = Field(default_factory=list, max_length=100)
    allergies: list[str] = Field(default_factory=list, max_length=50)
    labs: dict[str, Lab] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=20000)
    history_complete: bool = False
    synthetic: bool = False


class Criterion(BaseModel):
    kind: Literal["inclusion", "exclusion"] = "inclusion"
    attribute: str
    operator: Literal["gte", "lte", "gt", "lt", "eq", "contains", "review"]
    value: float | str | None = None
    unit: str | None = None
    original: str
    explicit: bool = True
    review_required: bool = False


class TrialInput(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=1000)
    conditions: list[str] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    sponsor: str = "Not reported"
    phase: str = "Not reported"
    status: str = "UNKNOWN"
    locations: list[str] = Field(default_factory=list)
    summary: str = ""
    eligibility: str = Field(default="", max_length=100000)
    min_age: float | None = None
    max_age: float | None = None
    sex: str = "ALL"
    source: str = "Local import"
    source_url: str | None = None
    retrieved_at: str | None = None
    synthetic: bool = False


class MatchRequest(BaseModel):
    patient_id: str
    limit: int = Field(default=10, ge=1, le=50)


class ImportRequest(BaseModel):
    condition: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=10, ge=1, le=50)


class Evidence(BaseModel):
    criterion: Criterion
    status: Literal["met", "not_met", "unknown"]
    patient_value: str
    explanation: str


class AgentLog(BaseModel):
    agent: str
    started_at: str
    duration_ms: float
    summary: str


class ProfileOutput(BaseModel):
    patient: PatientInput
    normalized_conditions: list[str]
    normalized_medications: list[str]
    entities: list[dict]
    missing_information: list[str]
    provenance: list[dict]


class Candidate(BaseModel):
    trial: TrialInput
    similarity: float


class RetrievalOutput(BaseModel):
    candidates: list[Candidate]
    provider: str


class ExtractionOutput(BaseModel):
    criteria_by_trial: dict[str, list[Criterion]]


class MatchResult(BaseModel):
    trial: TrialInput
    similarity: float
    score: float
    disposition: Literal["potential_match", "needs_review", "constraint_conflict"]
    evidence: list[Evidence]
    summary: str


class EvaluationOutput(BaseModel):
    results: list[MatchResult]
