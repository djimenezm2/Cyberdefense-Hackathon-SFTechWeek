-- Detections and analyzer windows
CREATE TABLE IF NOT EXISTS detections (
    ts DateTime64(3, 'UTC'),
    rule String,
    trace_id String,
    ip String,
    principal_id String,
    detail String
) ENGINE = MergeTree ORDER BY (ts, trace_id);

CREATE TABLE IF NOT EXISTS analyzer_windows (
    window_start DateTime64(3, 'UTC'),
    window_end DateTime64(3, 'UTC'),
    verdict String,
    model String,
    rationale String
) ENGINE = MergeTree ORDER BY (window_start);
