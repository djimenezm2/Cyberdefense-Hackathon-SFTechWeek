from datetime import datetime, timezone

from .broker import Broker
from .models import Action, AgentStep, IncidentDetail, IncidentSummary

TERMINAL = {"applied", "rejected", "not_reproduced"}
_INCIDENT_COLS = [
    "id",
    "updated_at",
    "status",
    "severity",
    "category",
    "opened_at",
    "title",
    "document",
]
_ACTION_COLS = [
    "ts",
    "guild_session_id",
    "incident_id",
    "operation",
    "args_hash",
    "outcome",
    "duration_ms",
    "on_behalf_of",
]


def _z(value) -> str:
    """Render a ClickHouse datetime (str or datetime) as an ISO-8601 Z string."""
    if isinstance(value, str):
        return value if value.endswith("Z") else value.replace(" ", "T") + "Z"
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string with a trailing Z, millisecond precision."""
    return _z(datetime.now(timezone.utc))


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string (Z or offset) into an aware UTC datetime."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class IncidentStore:
    """Incident documents (latest-wins) and the append-only agent audit."""

    def __init__(self, client, broker: Broker | None = None):
        self._client = client
        self._broker = broker

    def put(self, detail: IncidentDetail, step: AgentStep | None = None) -> None:
        """
        Insert a new incidents row carrying the full document and the core columns.

        Publishes `incident_update` when the incident is new or its status changed, and
        `step` when a step is given (it is appended to the document first).

        Args:
            detail (IncidentDetail): The incident document to store.
            step (AgentStep | None): A step recorded together with this write.
        """
        previous = self.get(detail.id) if self._broker else None
        if step is not None:
            detail.steps.append(step)
        row = [
            detail.id,
            datetime.now(timezone.utc),
            detail.status,
            detail.severity,
            detail.category,
            parse_iso(detail.opened_at),
            detail.title,
            detail.model_dump_json(),
        ]
        self._client.insert("incidents", [row], column_names=_INCIDENT_COLS)
        if self._broker is None:
            return
        if previous is None or previous.status != detail.status:
            self._broker.publish(
                "incident_update",
                {
                    "id": detail.id,
                    "status": detail.status,
                    "severity": detail.severity,
                    "title": detail.title,
                },
            )
        if step is not None:
            self._broker.publish("step", {"incident_id": detail.id, **step.model_dump()})

    def add_step(self, incident_id: str, step: AgentStep) -> None:
        """
        Append a step to an existing incident and publish it.

        Raises:
            KeyError: If the incident does not exist.
        """
        detail = self.get(incident_id)
        if detail is None:
            raise KeyError(incident_id)
        self.put(detail, step=step)

    def get(self, incident_id: str) -> IncidentDetail | None:
        """Return the latest document of an incident, or None when it does not exist."""
        res = self._client.query(
            "SELECT document FROM incidents FINAL WHERE id = {id:String}",
            parameters={"id": incident_id},
        )
        if not res.result_rows:
            return None
        return IncidentDetail.model_validate_json(res.result_rows[0][0])

    def list_summaries(self) -> list[IncidentSummary]:
        """Return the latest row of every incident, newest first."""
        res = self._client.query(
            "SELECT id, title, status, severity, category, opened_at "
            "FROM incidents FINAL ORDER BY opened_at DESC"
        )
        return [
            IncidentSummary(
                id=r[0], title=r[1], status=r[2], severity=r[3], category=r[4], opened_at=_z(r[5])
            )
            for r in res.result_rows
        ]

    def open_count(self) -> int:
        """Count incidents whose status is not terminal."""
        res = self._client.query(
            "SELECT count() FROM incidents FINAL WHERE status NOT IN "
            "('applied','rejected','not_reproduced')"
        )
        return int(res.result_rows[0][0]) if res.result_rows else 0

    def record_action(self, action: Action, *, guild_session_id: str, args_hash: str) -> None:
        """Append one row to the agent audit."""
        row = [
            parse_iso(action.ts),
            guild_session_id,
            action.incident_id,
            action.operation,
            args_hash,
            action.outcome,
            action.duration_ms,
            action.on_behalf_of,
        ]
        self._client.insert("agent_actions", [row], column_names=_ACTION_COLS)

    def list_actions(self, incident_id: str | None) -> list[Action]:
        """Return audit rows, oldest first, optionally for one incident."""
        columns = "SELECT ts, incident_id, operation, outcome, duration_ms, on_behalf_of FROM agent_actions"
        if incident_id:
            res = self._client.query(
                f"{columns} WHERE incident_id = {{id:String}} ORDER BY ts",
                parameters={"id": incident_id},
            )
        else:
            res = self._client.query(f"{columns} ORDER BY ts")
        return [
            Action(
                ts=_z(r[0]),
                incident_id=r[1],
                operation=r[2],
                outcome=r[3],
                duration_ms=int(r[4]),
                on_behalf_of=r[5],
            )
            for r in res.result_rows
        ]
