from .store import parse_iso

_PRINCIPALS = """
SELECT principal_id, count() AS requests, countIf(status >= 400) AS errors,
       uniqExact(ip) AS distinct_ips, uniqExact(route) AS distinct_routes,
       principal_id NOT IN (
         SELECT principal_id FROM http_requests
         WHERE auth_outcome = 'login_success' AND principal_id != ''
           AND ts <= {end:String}) AS new_principal
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


def _ch_text(value: str) -> str:
    """Render an ISO-8601 instant as ClickHouse DateTime64(3) text."""
    return parse_iso(value).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


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
    pr = db.query(_PRINCIPALS, parameters=params)
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
    }
