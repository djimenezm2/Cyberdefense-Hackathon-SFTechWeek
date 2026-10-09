import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
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
OUTPUT_TAIL = 2000
_COPY_IGNORE = shutil.ignore_patterns(".git", "node_modules")


def run_process(
    args: list[str], *, cwd: str, input: str | None, timeout: float, env: dict | None = None
) -> tuple[int, str]:
    """
    Run a command in its own process group and return its exit code and combined output.

    Raises:
        SandboxError: If the command cannot start or exceeds `timeout`; its group is killed.
    """
    try:
        proc = subprocess.Popen(
            args, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, start_new_session=True,
        )
    except OSError as exc:
        raise SandboxError(f"{args[0]} could not run: {exc}") from exc
    try:
        output, _ = proc.communicate(input, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise SandboxError(f"{' '.join(args)} timed out after {timeout}s") from None
    return proc.returncode, output


def spawn_process(args: list[str], *, cwd: str, env: dict, log_path: str) -> subprocess.Popen:
    """Start a long-running process in its own group, writing its output to `log_path`."""
    with open(log_path, "wb") as log:
        return subprocess.Popen(
            args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log,
            stderr=subprocess.STDOUT, start_new_session=True,
        )


def _tail(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()[-OUTPUT_TAIL:]
    except OSError:
        return ""


def stop_process(proc: subprocess.Popen) -> None:
    """Terminate a process group, killing it if it does not exit within five seconds."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    except ProcessLookupError:
        pass


def port_is_free(port: int) -> bool:
    """True when nothing accepts connections on 127.0.0.1:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def http_ready(base_url: str) -> bool:
    """True when the replica answers its version endpoint."""
    try:
        return httpx.get(f"{base_url}/rest/admin/application-version", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


class ReplicaBuilder:
    """
    Builds and runs a replica of the production source on the sandbox port.

    The source is copied without `.git` and `node_modules`; the production `node_modules` is
    linked in. A non-empty diff is applied with `git apply` and the server is rebuilt. Builds and
    the replica get only PATH, HOME and PORT, never the toolbox's environment.

    Args:
        settings (Settings): Source root, port and timeouts.
        run (Callable): Runs a command to completion; see `run_process`.
        spawn (Callable): Starts the replica server; see `spawn_process`.
        stop (Callable): Stops the replica server; see `stop_process`.
        probe (Callable): True once the replica answers; see `http_ready`.
        port_free (Callable): True when the sandbox port is unused; see `port_is_free`.
        sleep (Callable): Pause between readiness probes.
        workdir (str | None): Parent of the temporary replica directories.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        run=run_process,
        spawn=spawn_process,
        stop=stop_process,
        probe=http_ready,
        port_free=port_is_free,
        sleep=time.sleep,
        workdir: str | None = None,
    ):
        self._settings = settings
        self._run = run
        self._spawn = spawn
        self._stop = stop
        self._probe = probe
        self._port_free = port_free
        self._sleep = sleep
        self._workdir = workdir

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._settings.sandbox_port}"

    def _env(self, home: str) -> dict:
        return {"PATH": os.environ.get("PATH", ""), "HOME": home, "PORT": str(self._settings.sandbox_port)}

    def _prepare(self, src: str, diff: str, env: dict) -> None:
        root = self._settings.production_source_root
        shutil.copytree(root, src, symlinks=True, ignore=_COPY_IGNORE)
        if os.path.isdir(os.path.join(root, "node_modules")):
            os.symlink(os.path.join(root, "node_modules"), os.path.join(src, "node_modules"))
        if not diff:
            return
        timeout = self._settings.sandbox_build_timeout_s
        steps = (
            (["git", "apply", "--whitespace=nowarn", "-"], diff, "diff does not apply"),
            (["node_modules/.bin/tsc"], None, "patched source does not build"),
        )
        for args, stdin, failure in steps:
            code, output = self._run(args, cwd=src, input=stdin, timeout=timeout, env=env)
            if code != 0:
                raise PatchError(f"{failure}: {output[-OUTPUT_TAIL:]}")

    def _wait_ready(self, proc, log_path: str) -> None:
        deadline = time.monotonic() + self._settings.sandbox_start_timeout_s
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise SandboxError(
                    f"replica exited during startup with code {proc.poll()}: {_tail(log_path)}"
                )
            if self._probe(self.base_url):
                return
            self._sleep(0.5)
        raise SandboxError(
            f"replica not ready after {self._settings.sandbox_start_timeout_s}s: {_tail(log_path)}"
        )

    @contextmanager
    def build(self, diff: str) -> Iterator[Replica]:
        """
        Yield a running replica of production plus `diff`, then stop it and delete its files.

        Raises:
            PatchError: If the diff does not apply or the server does not build.
            SandboxError: If the port is taken, a step times out or the replica does not start.
        """
        port = self._settings.sandbox_port
        if not self._port_free(port):
            raise SandboxError(f"sandbox port {port} is already in use")
        tmp = tempfile.mkdtemp(prefix="rootlane-replica-", dir=self._workdir)
        proc = None
        try:
            src = os.path.join(tmp, "src")
            env = self._env(tmp)
            self._prepare(src, diff, env)
            log_path = os.path.join(tmp, "replica.log")
            proc = self._spawn(["node", "build/app.js"], cwd=src, env=env, log_path=log_path)
            self._wait_ready(proc, log_path)
            yield Replica(base_url=self.base_url, source_dir=src)
        finally:
            if proc is not None:
                self._stop(proc)
            shutil.rmtree(tmp, ignore_errors=True)


def build_sandbox(settings: Settings) -> "SandboxManager":
    """Wire the production sandbox: Juice Shop replicas on the sandbox port, bounded HTTP calls."""
    client = httpx.Client(timeout=settings.sandbox_request_timeout_s, trust_env=False)
    return SandboxManager(settings, builder=ReplicaBuilder(settings).build, client=client)


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
            SandboxError: If the replica cannot be built, started or reached.
        """
        self._acquire()
        try:
            with self._builder("") as replica:
                return self._replay(replica.base_url, reproduction)
        finally:
            self._lock.release()

    def _replay(self, base_url: str, reproduction: Reproduction) -> dict:
        try:
            return replay(self._client, base_url, reproduction)
        except httpx.HTTPError as exc:
            raise SandboxError(f"replay on the replica failed: {exc!r}") from exc

    def _scan(self, rule_path: str, paths: list[str], source_dir: str) -> int:
        present = [p for p in paths if os.path.isfile(os.path.join(source_dir, p))]
        if not present:
            return 0
        try:
            return self._semgrep(rule_path, present, cwd=source_dir)["findings"]
        except RuntimeError as exc:
            raise PatchError(f"rule could not run: {exc}") from exc

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
            PatchError: If the diff is malformed, does not apply or does not build, or the rule
                cannot run.
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
                    before = self._replay(old.base_url, reproduction)
                    semgrep_old = self._scan(rule_path, paths, old.source_dir)
                with self._builder(diff) as new:
                    after = self._replay(new.base_url, reproduction)
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
