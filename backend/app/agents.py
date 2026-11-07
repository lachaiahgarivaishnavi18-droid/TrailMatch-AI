from datetime import datetime, timezone
from time import perf_counter
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .schemas import (PatientInput, TrialInput, ProfileOutput, RetrievalOutput, ExtractionOutput,
                      EvaluationOutput, AgentLog)
from .nlp import understand, extract
from .retrieval import retrieve
from .evaluation import match_candidate


class State(TypedDict, total=False):
    patient: PatientInput
    trials: list[TrialInput]
    limit: int
    profile: ProfileOutput
    retrieval: RetrievalOutput
    extraction: ExtractionOutput
    evaluation: EvaluationOutput
    report: dict
    logs: list[dict]


def traced(name, function):
    def node(state: State):
        start = perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat()
        result, summary = function(state)
        log = AgentLog(agent=name, started_at=timestamp, duration_ms=round((perf_counter()-start)*1000, 2), summary=summary)
        return {**result, "logs": state.get("logs", []) + [log.model_dump()]}
    return node


def profile_node(s):
    profile = understand(s["patient"])
    return {"profile": profile}, f"Normalized profile; {len(profile.missing_information)} information gaps."


def retrieval_node(s):
    result = retrieve(s["profile"], s["trials"], s["limit"])
    return {"retrieval": result}, f"Retrieved {len(result.candidates)} candidates using {result.provider}."


def extraction_node(s):
    result = ExtractionOutput(criteria_by_trial={c.trial.id: extract(c.trial) for c in s["retrieval"].candidates})
    return {"extraction": result}, "Preserved source criteria; flagged unsupported logic for review."


def evaluation_node(s):
    results = [match_candidate(s["patient"], c, s["extraction"].criteria_by_trial[c.trial.id]) for c in s["retrieval"].candidates]
    order = {"potential_match": 0, "needs_review": 1, "constraint_conflict": 2}
    results.sort(key=lambda r: (order[r.disposition], -r.score))
    return {"evaluation": EvaluationOutput(results=results)}, f"Evaluated {sum(len(r.evidence) for r in results)} constraints with three-valued logic."


def explanation_node(s):
    report = {"profile": s["profile"].model_dump(), "results": [r.model_dump() for r in s["evaluation"].results],
              "retrieval_provider": s["retrieval"].provider,
              "disclaimer": "Clinical research support only. Scores are ranking signals, not eligibility probabilities. Final eligibility requires qualified clinical research review."}
    return {"report": report}, "Generated criterion-level evidence and research-only report."


builder = StateGraph(State)
nodes = [("Patient understanding", profile_node), ("Trial retrieval", retrieval_node),
         ("Criteria extraction", extraction_node), ("Constraint evaluation", evaluation_node), ("Evidence reporting", explanation_node)]
previous = START
for name, function in nodes:
    builder.add_node(name, traced(name, function))
    builder.add_edge(previous, name)
    previous = name
builder.add_edge(previous, END)
graph = builder.compile()


def run_matching(patient: PatientInput, trials: list[TrialInput], limit: int):
    state = graph.invoke({"patient": patient, "trials": trials, "limit": limit, "logs": []})
    return {**state["report"], "logs": state["logs"]}
