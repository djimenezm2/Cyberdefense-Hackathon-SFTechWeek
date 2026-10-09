import logging
import time
from datetime import datetime, timedelta, timezone

from .config import Settings
from .features import compute_features
from .models import AgentStep, IncidentDetail
from .store import IncidentStore, _z, now_iso

log = logging.getLogger(__name__)

_WINDOW_COLS = ["window_start", "window_end", "verdict", "model", "rationale"]
_QUIET = {"verdict": "ignore", "rationale": "No traffic in the window.", "model": ""}


class Analyzer:
    """Computes window features, asks the decider for a verdict, and escalates."""

    def __init__(self, settings: Settings, db, store: IncidentStore, decider, guild, broker):
        self._settings = settings
        self._db = db
        self._store = store
        self._decider = decider
        self.guild = guild
        self._broker = broker

    def run_once(self, now: datetime) -> None:
        """
        Analyze the window ending at `now`: store and publish the verdict, escalate if asked.

        Args:
            now (datetime): The window end.

        Raises:
            Exception: Whatever the database or the decider raises; nothing is stored then.
        """
        start_dt = now - timedelta(seconds=self._settings.analyze_interval_s)
        start, end = _z(start_dt), _z(now)
        features = compute_features(self._db, start, end)
        if features["principals"] or features["ips"]:
            decision = self._decider.decide(features)
        else:
            decision = _QUIET
        self._db.insert(
            "analyzer_windows",
            [[start_dt, now, decision["verdict"], decision["model"], decision["rationale"]]],
            column_names=_WINDOW_COLS,
        )
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
            self._open_incident(now, decision)

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

    def _open_incident(self, now: datetime, decision: dict) -> None:
        incident_id = f"inc_{now.strftime('%Y%m%d%H%M%S')}"
        detail = IncidentDetail(
            id=incident_id,
            title="Suspicious activity detected by continuous analysis",
            status="investigating",
            severity="high",
            category="unknown",
            opened_at=now_iso(),
            summary=decision["rationale"],
        )
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
