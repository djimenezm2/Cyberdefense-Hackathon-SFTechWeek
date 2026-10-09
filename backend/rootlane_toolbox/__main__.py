import argparse
import os
import re
import sys
from datetime import datetime, timezone
from typing import get_args

from .api.deps import state
from .core.config import Settings
from .core.models import IncidentDetail, Severity
from .storage.db import clickhouse_client
from .storage.migrate import MigrationConfigError, load_statements, prepare_statements, run_migrations
from .storage.store import IncidentStore, now_iso

CATEGORY_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,31}")


def _category(value: str) -> str:
    if not CATEGORY_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(f"invalid category: {value!r}")
    return value


def _build_store(settings: Settings) -> IncidentStore:
    return IncidentStore(clickhouse_client(settings), broker=state.broker)


def open_incident(argv: list[str]) -> int:
    """
    Create an `investigating` incident and print its id.

    Args:
        argv (list[str]): Arguments after the `open-incident` command.

    Returns:
        int: 0 on success; invalid arguments exit through argparse with status 2.
    """
    parser = argparse.ArgumentParser(prog="python -m rootlane_toolbox open-incident")
    parser.add_argument("--title", required=True)
    parser.add_argument("--severity", required=True, choices=get_args(Severity))
    parser.add_argument("--category", required=True, type=_category)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args(argv)
    store = _build_store(Settings.from_env(os.environ))
    incident_id = f"inc_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    store.put(
        IncidentDetail(
            id=incident_id,
            title=args.title,
            status="investigating",
            severity=args.severity,
            category=args.category,
            opened_at=now_iso(),
            summary=args.summary,
        )
    )
    print(incident_id)
    return 0


def main(argv: list[str]) -> int:
    """Run the CLI; the commands are `migrate` and `open-incident`."""
    if argv[:1] == ["open-incident"]:
        return open_incident(argv[1:])
    if argv[:1] != ["migrate"]:
        print("usage: python -m rootlane_toolbox migrate | open-incident ...", file=sys.stderr)
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
