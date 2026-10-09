import hashlib
import re
from pathlib import Path


class GuardError(Exception):
    """Raised when a request violates a safety guard."""


_LEADING_CTE = re.compile(r"^\s*with\b", re.IGNORECASE)
_FORBIDDEN = (
    "insert",
    "alter",
    "drop",
    "create",
    "delete",
    "update",
    "truncate",
    "attach",
    "detach",
    "optimize",
    "system",
    "grant",
    "rename",
)
_TABLE_FUNCTIONS = (
    "url",
    "s3",
    "s3Cluster",
    "file",
    "remote",
    "remoteSecure",
    "cluster",
    "clusterAllReplicas",
    "executable",
    "mysql",
    "postgresql",
    "jdbc",
    "odbc",
    "hdfs",
    "azureBlobStorage",
    "input",
    "numbers",
    "numbers_mt",
    "zeros",
    "generateRandom",
    "merge",
    "dictionary",
)
_TABLE_FUNCTION_CALL = re.compile(
    r"\b(?:" + "|".join(_TABLE_FUNCTIONS) + r")\s*\(", re.IGNORECASE
)
_CLAUSES = re.compile(r"\b(?:settings|format)\b|\binto\s+outfile\b", re.IGNORECASE)


def assert_read_only_sql(sql: str) -> str:
    """
    Return the trimmed SQL if it is a single read-only statement.

    Raises:
        GuardError: If the SQL is empty, multi-statement, commented, not a SELECT/WITH,
            or contains a write or DDL keyword.
    """
    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        raise GuardError("empty SQL")
    if ";" in text:
        raise GuardError("multiple statements are not allowed")
    if "--" in text or "/*" in text or "#" in text:
        raise GuardError("SQL comments are not allowed")
    lowered = text.lower()
    if not (lowered.startswith("select") or _LEADING_CTE.match(lowered)):
        raise GuardError("only SELECT/WITH queries are allowed")
    if any(re.search(rf"\b{kw}\b", lowered) for kw in _FORBIDDEN):
        raise GuardError("write or DDL keyword detected")
    if _TABLE_FUNCTION_CALL.search(text):
        raise GuardError("table functions are not allowed")
    if _CLAUSES.search(text):
        raise GuardError("SETTINGS, FORMAT and INTO OUTFILE are not allowed")
    return text


def resolve_source_path(root: str, rel_path: str) -> Path:
    """
    Resolve rel_path inside root.

    Raises:
        GuardError: If the path is empty, absolute, encoded, traverses upward or escapes root.
    """
    if not rel_path or rel_path.startswith("/") or ".." in rel_path or "%" in rel_path:
        raise GuardError(f"illegal path: {rel_path!r}")
    if "\x00" in rel_path:
        raise GuardError("illegal path: embedded NUL")
    base = Path(root).resolve()
    target = (base / rel_path).resolve()
    if base != target and base not in target.parents:
        raise GuardError(f"path escapes source root: {rel_path!r}")
    return target


def diff_hash(diff: str) -> str:
    """Stable short identifier for a unified diff, used as the proposal key."""
    return "p_" + hashlib.sha256(diff.encode("utf-8")).hexdigest()[:12]


def assert_verify_passed(verify_result: dict | None, diff: str) -> None:
    """
    Check that the last verification passed for exactly this diff.

    Raises:
        GuardError: If there is no passing verification for this diff.
    """
    if not verify_result or verify_result.get("passed") is not True:
        raise GuardError("no passing verification for this diff")
    if verify_result.get("hash") != diff_hash(diff):
        raise GuardError("verification does not match the proposed diff")


def assert_approved(approval: dict | None, proposal_hash: str) -> None:
    """
    Check that a human approved exactly this proposal.

    Raises:
        GuardError: If there is no approval, it is a rejection, or it is for another proposal.
    """
    if not approval or approval.get("decision") != "approve":
        raise GuardError("not approved")
    if approval.get("proposal_hash") != proposal_hash:
        raise GuardError("approval does not match this proposal")
