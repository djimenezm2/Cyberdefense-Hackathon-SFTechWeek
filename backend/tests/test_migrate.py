import pytest

from rootlane_toolbox import __main__ as cli
from rootlane_toolbox.migrate import (
    MigrationConfigError,
    load_statements,
    prepare_statements,
    run_migrations,
)

PASSWORD = "Str0ng-Passw0rd!"


def _prepare(**kw):
    args = dict(ro_user="agent_ro", ro_password=PASSWORD, database="rootlane")
    args.update(kw)
    return prepare_statements(load_statements(), **args)


def test_every_statement_is_idempotent_ddl():
    stmts = load_statements()
    assert stmts, "expected schema statements"
    creates = [s for s in stmts if s.upper().startswith("CREATE TABLE")]
    assert all("IF NOT EXISTS" in s.upper() for s in creates)
    assert any("CREATE USER IF NOT EXISTS __RO_USER__" in s for s in stmts)


def test_prepare_fills_user_password_and_database():
    stmts = _prepare(ro_user="reader", database="mydb")
    joined = "\n".join(stmts)
    assert PASSWORD in joined and "reader" in joined and "mydb.*" in joined
    assert "__" not in joined


def test_read_only_user_carries_the_query_caps():
    user_ddl = next(s for s in _prepare() if s.startswith("CREATE USER"))
    for setting in (
        "readonly = 1",
        "max_result_rows = 200",
        "result_overflow_mode = 'break'",
        "max_block_size = 50",
        "max_execution_time = 5",
    ):
        assert setting in user_ddl


@pytest.mark.parametrize(
    "kw",
    [
        {"ro_password": ""},
        {"ro_password": "has'quote-Passw0rd"},
        {"ro_password": "back\\slash-Passw0rd"},
        {"ro_user": "bad name; DROP"},
        {"database": "db`x"},
    ],
)
def test_prepare_refuses_unsafe_or_missing_values(kw):
    with pytest.raises(MigrationConfigError):
        _prepare(**kw)


def test_cli_refuses_without_ro_password_and_runs_no_ddl(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(cli, "clickhouse_client", lambda s: called.append("connect"))
    monkeypatch.setattr(cli, "run_migrations", lambda c, s: called.append("ddl"))
    monkeypatch.setattr(cli.os, "environ", {"CLICKHOUSE_HOST": "h"})
    assert cli.main(["migrate"]) == 1
    assert called == []
    assert "CLICKHOUSE_RO_PASSWORD" in capsys.readouterr().err


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
