import os

import pytest

from rootlane_toolbox.config import Settings
from rootlane_toolbox.db import clickhouse_client
from rootlane_toolbox.features import compute_features

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
