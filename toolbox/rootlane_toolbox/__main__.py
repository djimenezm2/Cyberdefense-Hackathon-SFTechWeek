import os
import sys

from .config import Settings
from .db import clickhouse_client
from .migrate import MigrationConfigError, load_statements, prepare_statements, run_migrations


def main(argv: list[str]) -> int:
    """Run the CLI; the only command is `migrate`."""
    if argv[:1] != ["migrate"]:
        print("usage: python -m rootlane_toolbox migrate", file=sys.stderr)
        return 2
    settings = Settings.from_env(os.environ)
    try:
        statements = prepare_statements(
            load_statements(),
            ro_user=settings.clickhouse_ro_user,
            ro_password=settings.clickhouse_ro_password,
            database=settings.clickhouse_database,
        )
    except MigrationConfigError as error:
        print(f"migrate refused: {error}", file=sys.stderr)
        return 1
    run_migrations(clickhouse_client(settings), statements)
    print(f"applied {len(statements)} statements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
