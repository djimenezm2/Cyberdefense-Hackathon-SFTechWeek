import re
from pathlib import Path

from clickhouse_connect.driver import Client

SCHEMA_DIR = Path(__file__).parent / "schema"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MigrationConfigError(Exception):
    """Raised when the migration inputs are missing or unsafe to put in DDL."""


def load_statements() -> list[str]:
    """Return every schema statement, ordered by filename, split on ';'."""
    statements: list[str] = []
    for path in sorted(SCHEMA_DIR.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
        statements.extend(s.strip() for s in body.split(";") if s.strip())
    return statements


def prepare_statements(
    statements: list[str], *, ro_user: str, ro_password: str, database: str
) -> list[str]:
    """
    Fill the read-only user placeholders.

    Args:
        statements (list[str]): Statements from `load_statements`.
        ro_user (str): Name of the read-only user.
        ro_password (str): Its password.
        database (str): The database the user may read.

    Returns:
        list[str]: Statements ready to run.

    Raises:
        MigrationConfigError: If the password is empty or contains `'` or `\\`, or a
            name is not a plain identifier.
    """
    if not ro_password:
        raise MigrationConfigError("CLICKHOUSE_RO_PASSWORD is required")
    if "'" in ro_password or "\\" in ro_password:
        raise MigrationConfigError("CLICKHOUSE_RO_PASSWORD must not contain ' or \\")
    for label, value in (("CLICKHOUSE_RO_USER", ro_user), ("CLICKHOUSE_DATABASE", database)):
        if not _IDENTIFIER.match(value):
            raise MigrationConfigError(f"{label} must be a plain identifier")
    replacements = {
        "__RO_USER__": ro_user,
        "__RO_PASSWORD__": ro_password,
        "__DATABASE__": database,
    }
    prepared = []
    for statement in statements:
        for placeholder, value in replacements.items():
            statement = statement.replace(placeholder, value)
        prepared.append(statement)
    return prepared


def run_migrations(client: Client, statements: list[str]) -> None:
    """Execute each schema statement against the admin client."""
    for sql in statements:
        client.command(sql)
