from rootlane_toolbox.features import compute_features
from tests.conftest import FakeDB


def test_features_map_per_principal_and_per_ip():
    db = FakeDB(
        responses={
            "GROUP BY principal_id": [["22", 12, 3, 2, 5, 1]],
            "GROUP BY ip": [["198.51.100.23", 40, 6, 3, 2, 9, 1]],
        }
    )
    f = compute_features(db, "2026-10-09T21:00:30Z", "2026-10-09T21:00:40Z")
    assert f["principals"][0] == {
        "principal_id": "22",
        "requests": 12,
        "errors": 3,
        "distinct_ips": 2,
        "distinct_routes": 5,
        "new_principal": 1,
    }
    assert f["ips"][0]["flagged_params"] == 1 and f["ips"][0]["distinct_routes"] == 9 and f["ips"][0]["auth_rejected"] == 3
    assert f["window_start"] == "2026-10-09T21:00:30Z"


def test_features_query_parameters_use_clickhouse_datetime_text():
    seen = []

    class SpyDB(FakeDB):
        def query(self, sql, parameters=None):
            seen.append(parameters)
            return super().query(sql, parameters)

    compute_features(SpyDB(), "2026-10-09T21:00:30Z", "2026-10-09T21:00:40.500Z")
    assert seen[0]["start"] == "2026-10-09 21:00:30.000"
    assert seen[0]["end"] == "2026-10-09 21:00:40.500"


def _sqls():
    seen = []

    class SpyDB(FakeDB):
        def query(self, sql, parameters=None):
            seen.append(sql)
            return super().query(sql, parameters)

    return seen, SpyDB


def test_new_principal_looks_back_over_earlier_requests_within_a_day():
    seen = []

    class SpyDB(FakeDB):
        def query(self, sql, parameters=None):
            seen.append((sql, parameters))
            return super().query(sql, parameters)

    compute_features(SpyDB(), "2026-10-09T21:00:30Z", "2026-10-09T21:00:40Z")
    sql, params = next(q for q in seen if "GROUP BY principal_id" in q[0])
    assert "auth_events" not in sql and "login_success" not in sql
    assert "ts <= {start:String}" in sql and "ts >= {lookback:String}" in sql
    assert params["lookback"] == "2026-10-08 21:00:30.000"


def test_feature_rows_are_capped_at_the_busiest_twenty():
    seen, SpyDB = _sqls()
    compute_features(SpyDB(), "2026-10-09T21:00:30Z", "2026-10-09T21:00:40Z")
    assert len(seen) == 2
    assert all("ORDER BY requests DESC LIMIT 20" in q for q in seen)
