from datetime import datetime, timezone

from rootlane_toolbox.config import Settings
from tests.conftest import FakeDB

AUTH = {"Authorization": "Bearer ingest-secret"}


def _settings(token="ingest-secret"):
    return Settings(ingest_token=token, admin_token="secret")


def _event(**kw):
    """An event exactly as target/telemetry/telemetry.ts builds it."""
    base = {
        "ts": "2026-10-09T21:00:31.120Z",
        "trace_id": "a1f3",
        "method": "GET",
        "route": "/rest/basket/:id",
        "path": "/rest/basket/22",
        "status": 200,
        "latency_ms": 18,
        "ip": "198.51.100.23",
        "user_agent": "curl/8",
        "has_token": True,
        "principal_id": "22",
        "auth_outcome": "accepted",
        "param_flags": ["meta_chars"],
    }
    base.update(kw)
    return base


def _post(client, payload, headers=AUTH):
    return client.post("/internal/events", json=payload, headers=headers)


def test_missing_server_token_is_503(make_app):
    client = make_app(settings=_settings(token=""))
    assert _post(client, {"events": [_event()]}).status_code == 503


def test_missing_or_wrong_bearer_is_401(make_app):
    client = make_app(settings=_settings())
    assert _post(client, {"events": [_event()]}, headers={}).status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert _post(client, {"events": [_event()]}, headers=wrong).status_code == 401
    assert _post(client, {"events": [_event()]}, headers={"Authorization": "ingest-secret"}).status_code == 401


def test_middleware_batch_is_inserted_into_http_requests(make_app):
    db = FakeDB()
    client = make_app(settings=_settings(), db=db)
    r = _post(client, {"events": [_event(), _event(trace_id="b7c2", status=401)]})
    assert r.status_code == 200 and r.json() == {"accepted": 2, "rejected": 0}
    rows = [dict(zip(db.columns["http_requests"], row)) for row in db.inserted["http_requests"]]
    assert [row["trace_id"] for row in rows] == ["a1f3", "b7c2"]
    first = rows[0]
    assert first["ts"] == datetime(2026, 10, 9, 21, 0, 31, 120000, tzinfo=timezone.utc)
    assert first["route"] == "/rest/basket/:id" and first["status"] == 200
    assert first["latency_ms"] == 18 and first["ip"] == "198.51.100.23"
    assert first["principal_id"] == "22" and first["auth_outcome"] == "accepted"
    assert first["param_flags"] == ["meta_chars"]
    assert set(db.columns["http_requests"]) == {
        "ts", "trace_id", "method", "route", "status", "latency_ms",
        "ip", "principal_id", "auth_outcome", "param_flags",
    }


def test_single_event_and_bare_list_are_accepted(make_app):
    db = FakeDB()
    client = make_app(settings=_settings(), db=db)
    assert _post(client, _event()).json()["accepted"] == 1
    assert _post(client, [_event(), _event()]).json()["accepted"] == 2
    assert len(db.inserted["http_requests"]) == 3


def test_sensitive_and_unknown_fields_never_reach_the_insert(make_app):
    db = FakeDB()
    client = make_app(settings=_settings(), db=db)
    event = _event(
        password="hunter2-value",
        token="eyJ-token-value",
        authorization="Bearer leaked-value",
        cookie="session=leaked-cookie",
        body={"email": "leaked-body@example.com"},
    )
    assert _post(client, {"events": [event]}).status_code == 200
    stored = repr(db.inserted) + repr(db.columns)
    for leaked in ("hunter2", "eyJ-token", "leaked-value", "leaked-cookie", "leaked-body"):
        assert leaked not in stored
    for key in ("password", "token", "authorization", "cookie", "body", "user_agent", "path"):
        assert key not in db.columns["http_requests"]


def test_defaults_fill_optional_derived_fields(make_app):
    db = FakeDB()
    client = make_app(settings=_settings(), db=db)
    minimal = {k: _event()[k] for k in ("ts", "trace_id", "method", "route", "status", "latency_ms", "ip")}
    assert _post(client, {"events": [minimal]}).json()["accepted"] == 1
    row = dict(zip(db.columns["http_requests"], db.inserted["http_requests"][0]))
    assert row["principal_id"] == "" and row["auth_outcome"] == "none" and row["param_flags"] == []


def test_invalid_events_are_counted_not_stored(make_app):
    db = FakeDB()
    client = make_app(settings=_settings(), db=db)
    bad = _event(status="not-a-number")
    r = _post(client, {"events": [_event(), bad, "junk"]})
    assert r.json() == {"accepted": 1, "rejected": 2}
    assert len(db.inserted["http_requests"]) == 1


def test_auth_fields_populate_auth_events(make_app):
    db = FakeDB()
    client = make_app(settings=_settings(), db=db)
    event = _event(jwt_alg="none", claimed_identity="22", principal_resolved=True)
    assert _post(client, {"events": [event, _event(trace_id="zz")]}).json()["accepted"] == 2
    assert len(db.inserted["auth_events"]) == 1
    row = dict(zip(db.columns["auth_events"], db.inserted["auth_events"][0]))
    assert row["jwt_alg"] == "none" and row["claimed_identity"] == "22"
    assert row["principal_resolved"] == 1 and row["event"] == "accepted"
    assert row["trace_id"] == "a1f3" and row["route"] == "/rest/basket/:id"


def test_non_json_object_payload_is_422(make_app):
    client = make_app(settings=_settings())
    assert _post(client, "just a string").status_code == 422


def test_non_ascii_bearer_is_401_not_500(make_app):
    client = make_app(settings=_settings())
    headers = {"Authorization": "Bearer ".encode() + "é".encode("latin-1")}
    assert _post(client, {"events": [_event()]}, headers=headers).status_code == 401


def test_out_of_range_numbers_reject_only_that_event(make_app):
    db = FakeDB()
    client = make_app(settings=_settings(), db=db)
    payload = {"events": [_event(), _event(latency_ms=2**32), _event(status=70000)]}
    assert _post(client, payload).json() == {"accepted": 1, "rejected": 2}
    assert len(db.inserted["http_requests"]) == 1
