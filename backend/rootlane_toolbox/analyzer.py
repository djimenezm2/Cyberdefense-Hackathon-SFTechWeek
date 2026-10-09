import logging
import time
from datetime import datetime, timedelta, timezone

from .config import Settings
from .features import compute_features
from .models import AgentStep, IncidentDetail
from .store import IncidentStore, _z, now_iso

log = logging.getLogger(__name__)

_WINDOW_COLS = ["window_start", "window_end", "verdict", "model", "rationale"]
INGEST_DELAY_S = 3
_VERDICTS = ("ignore", "watch", "escalate")


class Analyzer:
    """Computes window features, asks the decider for a verdict, and escalates."""

    def __init__(self, settings: Settings, db, store: IncidentStore, decider, guild, broker):
        self._settings = settings
        self._db = db
        self._store = store
        self._decider = decider
        self.guild = guild
        self._broker = broker
        self._last_end: datetime | None = None

    def run_once(self, now: datetime) -> None:
        """
        Analyze the window since the previous one, ending `INGEST_DELAY_S` before `now`.

        Stores and publishes the verdict, and escalates when asked. A failing decider
        yields a `watch` verdict.

        Args:
            now (datetime): The current time.

        Raises:
            Exception: Whatever the database raises; nothing is stored and the window
                is retried next cycle.
        """
        end_dt = now - timedelta(seconds=INGEST_DELAY_S)
        start_dt = self._last_end or end_dt - timedelta(seconds=self._settings.analyze_interval_s)
        start, end = _z(start_dt), _z(end_dt)
        features = compute_features(self._db, start, end)
        if features["principals"] or features["ips"]:
            decision = self._decide(features)
        else:
            decision = {
                "verdict": "ignore",
                "rationale": "No traffic in the window.",
                "model": self._settings.triage_model,
            }
        self._db.insert(
            "analyzer_windows",
            [[start_dt, end_dt, decision["verdict"], decision["model"], decision["rationale"]]],
            column_names=_WINDOW_COLS,
        )
        self._last_end = end_dt
        self._broker.publish(
            "verdict",
            {
                "window_start": start,
                "window_end": end,
                "verdict": decision["verdict"],
                "model": decision["model"],
                "rationale": decision["rationale"],
            },
        )
        if decision["verdict"] == "escalate":
            if self._store.open_count() == 0:
                self._open_incident(end_dt, decision)
            else:
                log.info("escalation skipped: an incident is already open")

    def _decide(self, features: dict) -> dict:
        try:
            decision = self._decider.decide(features)
            if decision["verdict"] not in _VERDICTS:
                raise ValueError(f"unknown verdict {decision['verdict']!r}")
            return {
                "verdict": decision["verdict"],
                "rationale": str(decision["rationale"]),
                "model": str(decision["model"]),
            }
        except Exception:
            log.exception("triage failed")
            return {
                "verdict": "watch",
                "rationale": "triage unavailable",
                "model": self._settings.triage_model,
            }

    def tick(self, now: datetime) -> None:
        """Run one cycle, logging instead of raising so the loop survives failures."""
        try:
            self.run_once(now)
        except Exception:
            log.exception("analysis cycle failed")

    def run_forever(self) -> None:
        """Analyze every `analyze_interval_s` seconds until the process ends."""
        while True:
            self.tick(datetime.now(timezone.utc))
            time.sleep(self._settings.analyze_interval_s)

    def _open_incident(self, at: datetime, decision: dict) -> None:
        incident_id = f"inc_{at.strftime('%Y%m%d%H%M%S')}"
        detail = IncidentDetail(
            id=incident_id,
            title="Suspicious activity detected by continuous analysis",
            status="investigating",
            severity="high",
            category="unknown",
            opened_at=now_iso(),
            summary=decision["rationale"],
        )
        self._store.put(detail)
        detail.guild_session_id = self.guild.start_session({"id": incident_id})
        step = None
        if detail.guild_session_id is None:
            step = AgentStep(
                ts=now_iso(),
                kind="context",
                summary="Guild session not started: trigger not configured or call failed.",
                outcome="error",
            )
        self._store.put(detail, step=step)
