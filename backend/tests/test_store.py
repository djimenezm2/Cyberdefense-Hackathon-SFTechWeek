from datetime import datetime, timezone

from rootlane_toolbox.models import Action, IncidentDetail
from rootlane_toolbox.store import TERMINAL, IncidentStore, now_iso, parse_iso


class Result:
    def __init__(self, rows):
        self.result_rows = rows


class FakeClient:
    """Captures inserts and serves canned query rows."""

    def __init__(self, rows=None):
        self.rows = {}
        self.columns = {}
        self.canned = rows or []
        self.queries = []

    def insert(self, table, data, column_names):
        self.rows.setdefault(table, []).extend(data)
        self.columns[table] = column_names

    def query(self, sql, parameters=None):
        self.queries.append((sql, parameters))
        return Result(self.canned)


def _detail(**kw):
    base = dict(
        id="inc_01",
        title="t",
        status="investigating",
        severity="high",
        category="identity",
        opened_at=now_iso(),
        summary="s",
    )
    base.update(kw)
    return IncidentDetail.model_validate(base)


def test_put_writes_core_columns_and_document():
    client = FakeClient()
    IncidentStore(client).put(_detail())
    record = dict(zip(client.columns["incidents"], client.rows["incidents"][0]))
    assert record["id"] == "inc_01"
    assert record["status"] == "investigating"
    assert isinstance(record["opened_at"], datetime)
    assert IncidentDetail.model_validate_json(record["document"]).id == "inc_01"


def test_get_returns_latest_document_or_none():
    doc = _detail(status="pending_approval").model_dump_json()
    store = IncidentStore(FakeClient(rows=[[doc]]))
    assert store.get("inc_01").status == "pending_approval"
    assert IncidentStore(FakeClient(rows=[])).get("nope") is None


def test_list_summaries_renders_datetimes_as_z_strings():
    opened = datetime(2026, 10, 9, 21, 0, 41, 120000, tzinfo=timezone.utc)
    client = FakeClient(rows=[["inc_01", "t", "investigating", "high", "identity", opened]])
    summary = IncidentStore(client).list_summaries()[0]
    assert summary.opened_at == "2026-10-09T21:00:41.120Z"


def test_open_count_reads_the_count():
    assert IncidentStore(FakeClient(rows=[[3]])).open_count() == 3
    assert IncidentStore(FakeClient(rows=[])).open_count() == 0


def test_record_action_appends_row():
    client = FakeClient()
    action = Action(
        ts=now_iso(),
        incident_id="inc_01",
        operation="query_events",
        outcome="ok",
        duration_ms=140,
        on_behalf_of="rootlane-agent",
    )
    IncidentStore(client).record_action(action, guild_session_id="gs_9c1", args_hash="abc")
    row = dict(zip(client.columns["agent_actions"], client.rows["agent_actions"][0]))
    assert row["operation"] == "query_events"
    assert row["guild_session_id"] == "gs_9c1"
    assert row["args_hash"] == "abc"


def test_now_iso_is_utc_z_with_milliseconds():
    value = now_iso()
    assert value.endswith("Z") and len(value) == len("2026-10-09T21:00:41.120Z")


def test_parse_iso_round_trips_z_strings():
    parsed = parse_iso("2026-10-09T21:00:41.120Z")
    assert parsed == datetime(2026, 10, 9, 21, 0, 41, 120000, tzinfo=timezone.utc)


def test_open_count_excludes_every_terminal_status():
    client = FakeClient(rows=[[0]])
    IncidentStore(client).open_count()
    assert set(client.queries[0][1]["terminal"]) == set(TERMINAL)
