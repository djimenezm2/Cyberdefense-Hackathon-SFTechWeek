import os

import pytest

from rootlane_toolbox.core.config import Settings
from rootlane_toolbox.storage.db import clickhouse_client
from rootlane_toolbox.analysis.features import compute_features

pytestmark = pytest.mark.integration

_COLS = [
    "ts", "trace_id", "method", "route", "status", "latency_ms",
    "ip", "principal_id", "auth_outcome", "param_flags",
]  # fmt: skip


@pytest.mark.skipif(not os.environ.get("CLICKHOUSE_HOST"), reason="needs live ClickHouse")
def test_features_aggregate_window_traffic():
    from datetime import datetime, timezone

    client = clickhouse_client(Settings.from_env(os.environ))
    trace = "p2-feature-test"
    ts = datetime(2020, 1, 1, 0, 0, 33, tzinfo=timezone.utc)
    client.insert(
        "http_requests",
        [[ts, trace, "GET", "/api/Cards", 200, 12, "198.51.100.23", "p2-test-22", "accepted", []]],
        column_names=_COLS,
    )
    try:
        f = compute_features(client, "2020-01-01T00:00:00Z", "2020-01-01T00:01:00Z")
        assert any(p["principal_id"] == "p2-test-22" for p in f["principals"])
        assert any(i["ip"] == "198.51.100.23" for i in f["ips"])
    finally:
        client.command("ALTER TABLE http_requests DELETE WHERE trace_id = 'p2-feature-test'")


@pytest.mark.skipif(not os.environ.get("CLICKHOUSE_HOST"), reason="needs live ClickHouse")
def test_new_principal_flags_only_principals_unseen_before_the_window():
    from datetime import datetime, timezone

    client = clickhouse_client(Settings.from_env(os.environ))
    trace = "p2-newprincipal-test"

    def row(second, principal):
        ts = datetime(2020, 1, 1, 0, 0, second, tzinfo=timezone.utc)
        return [ts, trace, "GET", "/x", 200, 1, "198.51.100.24", principal, "none", []]

    client.insert(
        "http_requests",
        [row(5, "p2-old"), row(33, "p2-old"), row(34, "p2-fresh")],
        column_names=_COLS,
    )
    try:
        f = compute_features(client, "2020-01-01T00:00:30Z", "2020-01-01T00:01:00Z")
        flags = {p["principal_id"]: p["new_principal"] for p in f["principals"]}
        assert flags["p2-old"] == 0 and flags["p2-fresh"] == 1
    finally:
        client.command(f"ALTER TABLE http_requests DELETE WHERE trace_id = '{trace}'")


@pytest.mark.skipif(not os.environ.get("CLICKHOUSE_HOST"), reason="needs live ClickHouse")
def test_unauthenticated_principals_uses_a_short_login_lookback():
    from datetime import datetime, timezone

    client = clickhouse_client(Settings.from_env(os.environ))
    trace = "p2-unauth-test"

    def row(minute, second, ip, principal, outcome, route="/x"):
        ts = datetime(2020, 1, 1, 0, minute, second, tzinfo=timezone.utc)
        return [ts, trace, "GET", route, 200, 1, ip, principal, outcome, []]

    login = "/rest/user/login"
    client.insert(
        "http_requests",
        [
            row(0, 25, "198.51.100.31", "", "login_success", login),
            row(0, 35, "198.51.100.31", "p2-recent", "accepted"),
            row(0, 0, "198.51.100.32", "", "login_success", login),
            row(5, 0, "198.51.100.32", "p2-stale", "accepted"),
            row(5, 1, "198.51.100.33", "p2-nologin", "accepted"),
        ],
        column_names=_COLS,
    )
    try:
        f = compute_features(
            client, "2020-01-01T00:04:30Z", "2020-01-01T00:06:00Z", login_lookback_s=120
        )
        hits = {p["principal_id"] for p in f["unauthenticated_principals"]}
        assert hits == {"p2-stale", "p2-nologin"}
        f = compute_features(
            client, "2020-01-01T00:00:30Z", "2020-01-01T00:01:00Z", login_lookback_s=120
        )
        assert f["unauthenticated_principals"] == []
    finally:
        client.command(f"ALTER TABLE http_requests DELETE WHERE trace_id = '{trace}'")
