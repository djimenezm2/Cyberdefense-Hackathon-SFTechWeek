from typing import Literal, Optional

from pydantic import BaseModel

Status = Literal[
    "investigating",
    "not_reproduced",
    "fix_failed",
    "pending_approval",
    "rejected",
    "applying",
    "applied",
]
Severity = Literal["low", "medium", "high", "critical"]
Verdict = Literal["ignore", "watch", "escalate"]
StepKind = Literal[
    "query",
    "read_source",
    "semgrep",
    "context",
    "replay",
    "verify",
    "propose",
    "approval",
    "apply",
    "lesson",
]
StepOutcome = Literal["ok", "error", "refused"]


class RpsPoint(BaseModel):
    t: str
    total: int
    errors: int
    auth_rejected: int


class AnalyzerState(BaseModel):
    last_window: str
    verdict: Verdict
    model: str


class AgentState(BaseModel):
    running: bool
    incident_id: Optional[str] = None


class Overview(BaseModel):
    rps_series: list[RpsPoint]
    open_incidents: int
    analyzer: AnalyzerState
    agent: AgentState


class Event(BaseModel):
    ts: str
    trace_id: str
    method: str
    route: str
    status: int
    latency_ms: int
    ip: str
    principal_id: str
    auth_outcome: str
    param_flags: list[str]


class Window(BaseModel):
    window_start: str
    window_end: str
    verdict: Verdict
    model: str
    rationale: str


class IncidentSummary(BaseModel):
    id: str
    title: str
    status: Status
    severity: Severity
    category: str
    opened_at: str


class TimelineEntry(BaseModel):
    ts: str
    method: str
    route: str
    status: int
    principal_id: str
    ip: str
    note: Optional[str] = None


class AgentStep(BaseModel):
    ts: str
    kind: StepKind
    summary: str
    outcome: StepOutcome


class EvidenceItem(BaseModel):
    kind: str
    ref: str
    text: str


class Hypothesis(BaseModel):
    text: str
    evidence: list[EvidenceItem]


class ReplicaResult(BaseModel):
    status: int
    summary: str


class Regression(BaseModel):
    passed: int
    failed: int


class Verification(BaseModel):
    replica_before: ReplicaResult
    replica_after: ReplicaResult
    regression: Regression
    semgrep_old: int
    semgrep_new: int


class Proposal(BaseModel):
    proposal_hash: str
    diff: str
    rule_yaml: str
    report: str


class Approval(BaseModel):
    approver: str
    decision: Literal["approve", "reject"]
    ts: str
    reason: Optional[str] = None
    proposal_hash: str


class ApplyResult(BaseModel):
    pr_url: Optional[str] = None
    production_status: Optional[int] = None
    production_summary: Optional[str] = None
    variants: list[str] = []


class IncidentDetail(BaseModel):
    id: str
    title: str
    status: Status
    severity: Severity
    category: str
    opened_at: str
    guild_session_id: Optional[str] = None
    summary: str
    timeline: list[TimelineEntry] = []
    steps: list[AgentStep] = []
    hypothesis: Optional[Hypothesis] = None
    verification: Optional[Verification] = None
    proposal: Optional[Proposal] = None
    approval: Optional[Approval] = None
    apply: Optional[ApplyResult] = None


class Action(BaseModel):
    ts: str
    incident_id: str
    operation: str
    outcome: str
    duration_ms: int
    on_behalf_of: str


class ApproveBody(BaseModel):
    approver: str


class RejectBody(BaseModel):
    approver: str
    reason: str
