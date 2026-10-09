from datetime import datetime, timedelta, timezone

import pytest

from rootlane_toolbox.analysis.analyzer import INGEST_DELAY_S, Analyzer
from rootlane_toolbox.analysis.decider import TriageError
from rootlane_toolbox.core.config import Settings
from rootlane_toolbox.storage.store import IncidentStore
from tests.conftest import FakeDB

NOW = datetime(2026, 10, 9, 21, 0, 40, tzinfo=timezone.utc)


class StubDecider:
    def __init__(self, verdict):
        self._v = verdict
        self.calls = 0

    def decide(self, features):
        self.calls += 1
        return {"verdict": self._v, "rationale": "r", "model": "akashml/glm"}


class BoomDecider:
    def decide(self, features):
        raise RuntimeError("model down")


class SpyGuild:
    def __init__(self, sid):
        self._sid = sid
        self.calls = []
        self.db = None
        self.stored_before_call = []

    def start_session(self, incident):
        self.calls.append(incident["id"])
        self.stored_before_call.append(bool(self.db.inserted.get("incidents")))
        return self._sid


class SpyBroker:
    def __init__(self):
        self.published = []

    def publish(self, event, data):
        self.published.append((event, data))


BUSY = {
    "GROUP BY principal_id": [["22", 10, 0, 1, 3, 1]],
    "GROUP BY ip": [["1.2.3.4", 10, 0, 0, 1, 3, 0]],
}


def _analyzer(verdict, guild_sid, responses=BUSY, decider=None):
    db = FakeDB(responses=responses)
    broker = SpyBroker()
    store = IncidentStore(db, broker=broker)
    decider = decider or StubDecider(verdict)
    guild = SpyGuild(guild_sid)
    guild.db = db
    a = Analyzer(Settings(), db, store, decider, guild, broker)
    return a, db, broker, decider


def test_verdict_is_stored_and_published():
    a, db, broker, _ = _analyzer("watch", None)
    a.run_once(now=NOW)
    assert db.inserted["analyzer_windows"][0][2] == "watch"
    assert broker.published[0][0] == "verdict"
    assert broker.published[0][1]["rationale"] == "r"
    assert "incidents" not in db.inserted


def test_window_bounds_are_stored_as_datetimes():
    a, db, _, _ = _analyzer("watch", None)
    a.run_once(now=NOW)
    start, end = db.inserted["analyzer_windows"][0][:2]
    assert end == NOW - timedelta(seconds=INGEST_DELAY_S)
    assert (end - start).total_seconds() == 10


def test_escalate_opens_incident_and_starts_guild():
    a, db, broker, _ = _analyzer("escalate", "gs_test")
    a.run_once(now=NOW)
    assert db.inserted["incidents"]
    assert len(a.guild.calls) == 1
    assert '"guild_session_id":"gs_test"' in db.inserted["incidents"][-1][-1]
    assert "incident_update" in [e for e, _ in broker.published]


def test_escalate_opens_incident_even_when_guild_unavailable():
    a, db, _, _ = _analyzer("escalate", None)
    a.run_once(now=NOW)
    doc = db.inserted["incidents"][-1][-1]
    assert '"guild_session_id":null' in doc
    assert "Guild session not started" in doc


def test_incident_ids_are_unique_across_windows():
    a, db, _, _ = _analyzer("escalate", None)
    a.run_once(now=NOW)
    a.run_once(now=datetime(2026, 10, 9, 21, 0, 50, tzinfo=timezone.utc))
    ids = [row[0] for row in db.inserted["incidents"]]
    assert len(set(ids)) == 2


def test_empty_window_is_ignored_without_calling_the_decider():
    a, db, _, decider = _analyzer("escalate", None, responses={})
    a.run_once(now=NOW)
    assert decider.calls == 0
    assert db.inserted["analyzer_windows"][0][2] == "ignore"
    assert db.inserted["analyzer_windows"][0][3] == Settings().triage_model


def test_tick_swallows_a_failing_cycle_while_run_once_raises():
    class BoomDB(FakeDB):
        def query(self, sql, parameters=None):
            raise RuntimeError("db down")

    broker = SpyBroker()
    db = BoomDB()
    a = Analyzer(Settings(), db, IncidentStore(db), StubDecider("x"), SpyGuild(None), broker)
    with pytest.raises(RuntimeError):
        a.run_once(now=NOW)
    a.tick(now=NOW)
    assert "analyzer_windows" not in db.inserted


@pytest.mark.parametrize("decider", [BoomDecider(), StubDecider("panic")])
def test_triage_failure_stores_and_streams_a_watch_verdict(decider):
    a, db, broker, _ = _analyzer("x", None, decider=decider)
    a.run_once(now=NOW)
    row = db.inserted["analyzer_windows"][0]
    assert row[2] == "watch" and row[3] == Settings().triage_model
    assert row[4] == "triage unavailable"
    assert broker.published[0][1]["rationale"] == "triage unavailable"
    assert "incidents" not in db.inserted


def test_triage_error_reason_is_stored_as_the_rationale():
    class Reasoned:
        def decide(self, features):
            raise TriageError("triage timed out")

    a, db, broker, _ = _analyzer("x", None, decider=Reasoned())
    a.run_once(now=NOW)
    assert db.inserted["analyzer_windows"][0][4] == "triage timed out"
    assert broker.published[0][1]["rationale"] == "triage timed out"


def test_windows_are_contiguous_across_cycles():
    a, db, _, _ = _analyzer("watch", None)
    a.run_once(now=NOW)
    a.run_once(now=NOW + timedelta(seconds=13))
    first, second = db.inserted["analyzer_windows"]
    assert second[0] == first[1]
    assert (second[1] - second[0]).total_seconds() == 13


def test_failed_cycle_does_not_advance_the_window():
    class FlakyDB(FakeDB):
        fail = False

        def query(self, sql, parameters=None):
            if self.fail:
                raise RuntimeError("db down")
            return super().query(sql, parameters)

    db = FlakyDB(responses=BUSY)
    broker = SpyBroker()
    a = Analyzer(Settings(), db, IncidentStore(db, broker=broker), StubDecider("watch"),
                 SpyGuild(None), broker)
    a.run_once(now=NOW)
    db.fail = True
    a.tick(now=NOW + timedelta(seconds=10))
    db.fail = False
    a.run_once(now=NOW + timedelta(seconds=20))
    rows = db.inserted["analyzer_windows"]
    assert len(rows) == 2 and rows[1][0] == rows[0][1]


def test_incident_is_stored_before_the_guild_session_starts():
    a, db, _, _ = _analyzer("escalate", "gs_1")
    a.run_once(now=NOW)
    assert a.guild.stored_before_call == [True]
    assert len(db.inserted["incidents"]) == 2
    assert '"guild_session_id":null' in db.inserted["incidents"][0][-1]
    assert '"guild_session_id":"gs_1"' in db.inserted["incidents"][1][-1]


def test_failed_guild_start_is_recorded_on_the_stored_incident():
    a, db, _, _ = _analyzer("escalate", None)
    a.run_once(now=NOW)
    assert "Guild session not started" in db.inserted["incidents"][-1][-1]


def test_skipped_escalation_is_logged(caplog):
    open_rows = {"FROM incidents FINAL WHERE status NOT IN": [[1]], **BUSY}
    a, _, _, _ = _analyzer("escalate", None, responses=open_rows)
    with caplog.at_level("INFO"):
        a.run_once(now=NOW)
    assert "escalation skipped" in caplog.text


def test_escalate_while_an_incident_is_open_opens_no_new_one():
    open_rows = {"FROM incidents FINAL WHERE status NOT IN": [[1]], **BUSY}
    a, db, broker, _ = _analyzer("escalate", "gs_1", responses=open_rows)
    a.run_once(now=NOW)
    assert db.inserted["analyzer_windows"][0][2] == "escalate"
    assert broker.published[0][1]["verdict"] == "escalate"
    assert "incidents" not in db.inserted
    assert a.guild.calls == []
