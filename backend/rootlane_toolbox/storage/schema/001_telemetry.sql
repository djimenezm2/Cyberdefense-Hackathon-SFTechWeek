-- Request and auth telemetry
CREATE TABLE IF NOT EXISTS http_requests (
    ts DateTime64(3, 'UTC'),
    trace_id String,
    method String,
    route String,
    status UInt16,
    latency_ms UInt32,
    ip String,
    principal_id String,
    auth_outcome String,
    param_flags Array(String)
) ENGINE = MergeTree ORDER BY (ts, trace_id);

CREATE TABLE IF NOT EXISTS auth_events (
    ts DateTime64(3, 'UTC'),
    trace_id String,
    event String,
    jwt_alg String,
    claimed_identity String,
    principal_resolved UInt8,
    status UInt16,
    route String,
    ip String
) ENGINE = MergeTree ORDER BY (ts, trace_id);
