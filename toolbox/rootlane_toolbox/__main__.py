import os
import sys

from .config import Settings
from .db import clickhouse_client
from .migrate import load_statements, run_migrations


def main(argv: list[str]) -> int:
    """Run the CLI; the only command is `migrate`."""
    if argv[:1] != ["migrate"]:
        print("usage: python -m rootlane_toolbox migrate", file=sys.stderr)
        return 2
    settings = Settings.from_env(os.environ)
    client = clickhouse_client(settings)
    statements = [
        s.replace("__RO_PASSWORD__", settings.clickhouse_ro_password) for s in load_statements()
    ]
    run_migrations(client, statements)
    print(f"applied {len(statements)} statements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
