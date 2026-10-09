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
    ts = datetime(2026, 10, 9, 21, 0, 33, tzinfo=timezone.utc)
    client.insert(
        "http_requests",
        [[ts, trace, "GET", "/api/Cards", 200, 12, "198.51.100.23", "p2-test-22", "accepted", []]],
        column_names=_COLS,
    )
    try:
        f = compute_features(client, "2026-10-09T21:00:00Z", "2026-10-09T21:01:00Z")
        assert any(p["principal_id"] == "p2-test-22" for p in f["principals"])
        assert any(i["ip"] == "198.51.100.23" for i in f["ips"])
    finally:
        client.command("ALTER TABLE http_requests DELETE WHERE trace_id = 'p2-feature-test'")
