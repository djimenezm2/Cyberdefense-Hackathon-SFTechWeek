import os
import re
import tempfile
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..core.config import Settings
from ..core.guards import GuardError, diff_hash
from .regression import run_smoke
from .semgrep_runner import run_semgrep

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
DROPPED_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "upgrade",
    "te",
    "trailer",
    "expect",
    "proxy-authorization",
    "proxy-connection",
}
EXCERPT_CHARS = 500
_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_UNSAFE_PATH = re.compile(r"[\s\\\x00-\x1f\x7f]")


class Reproduction(BaseModel):
    """
    The agent's reproduction request, replayed only against a replica.

    Attributes:
        method (str): HTTP method, upper-cased.
        path (str): Origin-relative path with optional query, e.g. `/rest/basket/2?x=1`.
        headers (dict[str, str]): Request headers; host and hop-by-hop headers are dropped.
        body (Any): None, a string sent as-is, or a JSON value.
        expected_blocked_status (int): The 4xx status that means the request was rejected.
    """

    method: str
    path: str
    headers: dict[str, str] = {}
    body: Any = None
    expected_blocked_status: int = Field(ge=400, le=499)

    @field_validator("method")
    @classmethod
    def _method(cls, value: str) -> str:
        method = value.upper()
        if method not in METHODS:
            raise ValueError(f"method not allowed: {value!r}")
        return method

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        parts = urlsplit(value)
        if (not value.startswith("/") or value.startswith("//") or parts.scheme or parts.netloc
                or _UNSAFE_PATH.search(value)):
            raise ValueError(f"path must be origin-relative: {value!r}")
        return value

    @field_validator("headers")
    @classmethod
    def _headers(cls, value: dict[str, str]) -> dict[str, str]:
        kept = {}
        for name, header in value.items():
            if not _TOKEN.match(name) or "\r" in header or "\n" in header:
                raise ValueError(f"illegal header: {name!r}")
            if name.lower() not in DROPPED_HEADERS:
                kept[name] = header
        return kept


def parse_reproduction(data: dict) -> Reproduction:
    """
    Validate an agent-supplied reproduction.

    Raises:
        GuardError: If any field is missing or unsafe.
    """
    try:
        return Reproduction.model_validate(data)
    except ValidationError as exc:
        reasons = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise GuardError(f"invalid reproduction: {reasons}") from None


def replica_url(base_url: str, path: str) -> str:
    """
    Join the replica base URL and a reproduction path.

    Raises:
        GuardError: If the result would point anywhere but the replica.
    """
    url = httpx.URL(base_url + path)
    base = httpx.URL(base_url)
    if (url.scheme, url.host, url.port) != (base.scheme, base.host, base.port):
        raise GuardError(f"path leaves the replica: {path!r}")
    return str(url)


def replay(client: httpx.Client, base_url: str, reproduction: Reproduction) -> dict:
    """
    Send the reproduction to a replica.

    Args:
        client (httpx.Client): HTTP client with bounded timeouts.
        base_url (str): The replica origin, e.g. `http://127.0.0.1:3001`.
        reproduction (Reproduction): The validated request.

    Returns:
        dict: `{"status": int, "excerpt": str}`, the excerpt being the first characters of the body.
    """
    kwargs: dict[str, Any] = {"headers": reproduction.headers, "follow_redirects": False}
    if isinstance(reproduction.body, str):
        kwargs["content"] = reproduction.body
    elif reproduction.body is not None:
        kwargs["json"] = reproduction.body
    url = replica_url(base_url, reproduction.path)
    response = client.request(reproduction.method, url, **kwargs)
    return {"status": response.status_code, "excerpt": response.text[:EXCERPT_CHARS]}


class SandboxError(Exception):
    """Raised when a replica cannot be built, started or reached."""


class PatchError(SandboxError):
    """Raised when the candidate diff does not apply or does not build."""


class SandboxBusy(SandboxError):
    """Raised when another replica is still running."""


@dataclass
class Replica:
    """A running replica: its origin and the source tree it was built from."""

    base_url: str
    source_dir: str


_DIFF_PATH = re.compile(r"^(?:---|\+\+\+) (?:[ab]/)?(\S+)", re.MULTILINE)


def touched_files(diff: str) -> list[str]:
    """
    List the repo-relative files a unified diff touches, in order of appearance.

    Raises:
        PatchError: If the diff names no file or a path outside the tree.
    """
    paths = []
    for path in _DIFF_PATH.findall(diff):
        if path == "/dev/null":
            continue
        if path.startswith("/") or ".." in path.split("/"):
            raise PatchError(f"diff path outside the source tree: {path!r}")
        if path not in paths:
            paths.append(path)
    if not paths:
        raise PatchError("diff names no file")
    return paths


Builder = Callable[[str], AbstractContextManager[Replica]]


class SandboxManager:
    """
    Builds throwaway replicas of production and checks the agent's reproduction against them.

    One replica runs at a time; each one is torn down by its builder when the check ends.

    Args:
        settings (Settings): Runtime configuration.
        builder (Builder): `builder(diff)` yields a running replica of production plus `diff`.
        client (httpx.Client): HTTP client used for the replay and the smoke suite.
        semgrep (Callable): `semgrep(config, paths, *, cwd)` returning `{"findings": int, ...}`.
        smoke (Callable): `smoke(client, base_url)` returning `{"passed", "failed", "failures"}`.
        lock_timeout_s (float): How long a caller waits for the running replica to finish.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        builder: Builder,
        client: httpx.Client,
        semgrep: Callable[..., dict] = run_semgrep,
        smoke: Callable[[httpx.Client, str], dict] = run_smoke,
        lock_timeout_s: float = 300.0,
    ):
        self._settings = settings
        self._builder = builder
        self._client = client
        self._semgrep = semgrep
        self._smoke = smoke
        self._lock_timeout_s = lock_timeout_s
        self._lock = threading.Lock()

    def _acquire(self) -> None:
        if not self._lock.acquire(timeout=self._lock_timeout_s):
            raise SandboxBusy("another replica is running")

    def reproduce(self, reproduction: Reproduction) -> dict:
        """
        Replay the reproduction on a fresh, unpatched replica.

        Returns:
            dict: `{"status": int, "excerpt": str}`.

        Raises:
            SandboxBusy: If another replica is still running.
            SandboxError: If the replica cannot be built or started.
        """
        self._acquire()
        try:
            with self._builder("") as replica:
                return replay(self._client, replica.base_url, reproduction)
        finally:
            self._lock.release()

    def _scan(self, rule_path: str, paths: list[str], source_dir: str) -> int:
        present = [p for p in paths if os.path.isfile(os.path.join(source_dir, p))]
        if not present:
            return 0
        return self._semgrep(rule_path, present, cwd=source_dir)["findings"]

    def verify_patch(self, diff: str, rule_yaml: str, reproduction: Reproduction) -> dict:
        """
        Check a candidate patch against the stored reproduction, the smoke suite and its rule.

        Passes when the reproduction is not blocked before the patch and blocked after it, the
        smoke suite is clean on the patched replica, and the rule fires on the old touched files
        and is silent on the new ones.

        Returns:
            dict: `hash`, `passed`, `exploit_before`, `exploit_after`, `replica_before`,
                `replica_after`, `regression`, `semgrep_old`, `semgrep_new`.

        Raises:
            PatchError: If the diff is malformed, does not apply or does not build.
            SandboxBusy: If another replica is still running.
            SandboxError: If a replica cannot be built or started.
        """
        paths = touched_files(diff)
        blocked = reproduction.expected_blocked_status
        self._acquire()
        try:
            with tempfile.TemporaryDirectory(prefix="rootlane-rule-") as rule_dir:
                rule_path = os.path.join(rule_dir, "rule.yaml")
                with open(rule_path, "w", encoding="utf-8") as fh:
                    fh.write(rule_yaml)
                with self._builder("") as old:
                    before = replay(self._client, old.base_url, reproduction)
                    semgrep_old = self._scan(rule_path, paths, old.source_dir)
                with self._builder(diff) as new:
                    after = replay(self._client, new.base_url, reproduction)
                    regression = self._smoke(self._client, new.base_url)
                    semgrep_new = self._scan(rule_path, paths, new.source_dir)
        finally:
            self._lock.release()
        passed = (
            before["status"] != blocked
            and after["status"] == blocked
            and regression["failed"] == 0
            and semgrep_old > 0
            and semgrep_new == 0
        )
        return {
            "hash": diff_hash(diff),
            "passed": passed,
            "exploit_before": before["status"],
            "exploit_after": after["status"],
            "replica_before": before,
            "replica_after": after,
            "regression": regression,
            "semgrep_old": semgrep_old,
            "semgrep_new": semgrep_new,
        }
