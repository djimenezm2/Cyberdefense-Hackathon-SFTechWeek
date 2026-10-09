from rootlane_toolbox.migrate import load_statements, run_migrations


def test_every_statement_is_idempotent_ddl():
    stmts = load_statements()
    assert stmts, "expected schema statements"
    creates = [s for s in stmts if s.upper().startswith("CREATE TABLE")]
    assert all("IF NOT EXISTS" in s.upper() for s in creates)
    assert any("CREATE USER IF NOT EXISTS agent_ro" in s for s in stmts)


def test_run_migrations_passes_each_statement_to_client():
    class FakeClient:
        def __init__(self):
            self.commands = []

        def command(self, sql):
            self.commands.append(sql)

    client = FakeClient()
    stmt = "CREATE TABLE IF NOT EXISTS x (a UInt8) ENGINE = MergeTree ORDER BY a"
    run_migrations(client, [stmt])
    assert client.commands == [stmt]
