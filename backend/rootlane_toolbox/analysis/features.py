from datetime import timedelta

from ..storage.store import parse_iso

LOOKBACK = timedelta(hours=24)

_PRINCIPALS = """
SELECT principal_id, count() AS requests, countIf(status >= 400) AS errors,
       uniqExact(ip) AS distinct_ips, uniqExact(route) AS distinct_routes,
       principal_id NOT IN (
         SELECT principal_id FROM http_requests
         WHERE principal_id != ''
           AND ts >= {lookback:String} AND ts <= {start:String}) AS new_principal
FROM http_requests
WHERE ts > {start:String} AND ts <= {end:String} AND principal_id != ''
GROUP BY principal_id
ORDER BY requests DESC LIMIT 20
"""
_IPS = """
SELECT ip, count() AS requests, countIf(status >= 400) AS errors,
       countIf(auth_outcome = 'rejected') AS auth_rejected,
       uniqExact(principal_id) AS distinct_principals, uniqExact(route) AS distinct_routes,
       countIf(length(param_flags) > 0) AS flagged_params
FROM http_requests
WHERE ts > {start:String} AND ts <= {end:String}
GROUP BY ip
ORDER BY requests DESC LIMIT 20
"""
_UNAUTHENTICATED = """
SELECT r.principal_id, r.ip
FROM (
  SELECT principal_id, ip, min(ts) AS first_ts
  FROM http_requests
  WHERE ts > {start:String} AND ts <= {end:String} AND principal_id != ''
    AND status >= 200 AND status < 300
  GROUP BY (principal_id, ip)
) AS r
LEFT JOIN (
  SELECT ip, min(ts) AS login_ts
  FROM http_requests
  WHERE auth_outcome = 'login_success'
    AND ts >= {lookback:String} AND ts <= {end:String}
  GROUP BY (ip)
) AS l ON r.ip = l.ip
WHERE l.ip = '' OR l.login_ts > r.first_ts
ORDER BY r.first_ts LIMIT 20
"""


def _ch_text(value) -> str:
    """Render an ISO-8601 string or datetime as ClickHouse DateTime64(3) text."""
    moment = parse_iso(value) if isinstance(value, str) else value
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def compute_features(db, window_start: str, window_end: str) -> dict:
    """
    Generic per-principal and per-IP behavioural features over a window.

    Args:
        db: ClickHouse client.
        window_start (str): Exclusive ISO-8601 lower bound.
        window_end (str): Inclusive ISO-8601 upper bound.

    Returns:
        dict: Window bounds plus two lists of scenario-agnostic feature rows.
    """
    params = {"start": _ch_text(window_start), "end": _ch_text(window_end)}
    lookback = _ch_text(parse_iso(window_start) - LOOKBACK)
    pr = db.query(_PRINCIPALS, parameters={**params, "lookback": lookback})
    ips = db.query(_IPS, parameters=params)
    principals = [
        {
            "principal_id": r[0],
            "requests": int(r[1]),
            "errors": int(r[2]),
            "distinct_ips": int(r[3]),
            "distinct_routes": int(r[4]),
            "new_principal": int(r[5]),
        }
        for r in pr.result_rows
    ]
    unauthenticated = db.query(_UNAUTHENTICATED, parameters={**params, "lookback": lookback})
    ip_rows = [
        {
            "ip": r[0],
            "requests": int(r[1]),
            "errors": int(r[2]),
            "auth_rejected": int(r[3]),
            "distinct_principals": int(r[4]),
            "distinct_routes": int(r[5]),
            "flagged_params": int(r[6]),
        }
        for r in ips.result_rows
    ]
    return {
        "window_start": window_start,
        "window_end": window_end,
        "principals": principals,
        "ips": ip_rows,
        "unauthenticated_principals": [
            {"principal_id": r[0], "ip": r[1]} for r in unauthenticated.result_rows
        ],
    }
