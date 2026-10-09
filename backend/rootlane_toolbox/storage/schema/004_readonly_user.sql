-- Read-only user for query_events; placeholders are filled at migrate time
CREATE USER IF NOT EXISTS __RO_USER__ IDENTIFIED WITH sha256_password BY '__RO_PASSWORD__' SETTINGS readonly = 1, max_result_rows = 200, result_overflow_mode = 'break', max_block_size = 50, max_execution_time = 5;
GRANT SELECT ON __DATABASE__.* TO __RO_USER__;
