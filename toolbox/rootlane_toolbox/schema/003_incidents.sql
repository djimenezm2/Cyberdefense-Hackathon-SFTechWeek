-- Incident documents and the agent audit
CREATE TABLE IF NOT EXISTS incidents (
    id String,
    updated_at DateTime64(3, 'UTC'),
    status String,
    severity String,
    category String,
    opened_at DateTime64(3, 'UTC'),
    title String,
    document String
) ENGINE = ReplacingMergeTree(updated_at) ORDER BY id;

CREATE TABLE IF NOT EXISTS agent_actions (
    ts DateTime64(3, 'UTC'),
    guild_session_id String,
    incident_id String,
    operation String,
    args_hash String,
    outcome String,
    duration_ms UInt32,
    on_behalf_of String
) ENGINE = MergeTree ORDER BY (ts, operation);
