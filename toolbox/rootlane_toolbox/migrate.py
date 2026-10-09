from pathlib import Path

from clickhouse_connect.driver import Client

SCHEMA_DIR = Path(__file__).parent / "schema"


def load_statements() -> list[str]:
    """Return every schema statement, ordered by filename, split on ';'."""
    statements: list[str] = []
    for path in sorted(SCHEMA_DIR.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
        statements.extend(s.strip() for s in body.split(";") if s.strip())
    return statements


def run_migrations(client: Client, statements: list[str]) -> None:
    """Execute each schema statement against the admin client."""
    for sql in statements:
        client.command(sql)
