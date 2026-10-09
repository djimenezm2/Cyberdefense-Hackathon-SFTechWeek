-- Read-only user for query_events; the password placeholder is filled at migrate time
CREATE USER IF NOT EXISTS agent_ro IDENTIFIED WITH sha256_password BY '__RO_PASSWORD__' SETTINGS readonly = 1;
GRANT SELECT ON rootlane.* TO agent_ro;
