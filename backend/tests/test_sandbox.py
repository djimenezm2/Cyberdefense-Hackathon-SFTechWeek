import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from rootlane_toolbox.core.config import Settings
from rootlane_toolbox.core.guards import diff_hash
from rootlane_toolbox.integrations.sandbox import (
    PatchError,
    Replica,
    SandboxBusy,
    SandboxError,
    SandboxManager,
    parse_reproduction,
    touched_files,
)

REPRO = parse_reproduction({"method": "GET", "path": "/rest/basket/22", "headers": {},
                            "body": None, "expected_blocked_status": 401})
DIFF = (
    "diff --git a/lib/insecurity.ts b/lib/insecurity.ts\n"
    "--- a/lib/insecurity.ts\n+++ b/lib/insecurity.ts\n@@ -1 +1 @@\n-a\n+b\n"
)


class Harness:
    def __init__(self, before=200, after=401, semgrep_old=2, semgrep_new=0, reg_failed=0,
                 fail_in=None):
        self.status = {"old": before, "new": after}
        self.findings = {"old": semgrep_old, "new": semgrep_new}
        self.reg_failed = reg_failed
        self.fail_in = fail_in
        self.built, self.torn_down, self.semgrep_calls = [], [], []
        self.root = Path(tempfile.mkdtemp(prefix="sandbox-test-"))
        for name in ("old", "new"):
            (self.root / name / "lib").mkdir(parents=True)
            (self.root / name / "lib" / "insecurity.ts").write_text("x")

    @contextmanager
    def builder(self, diff):
        name = "new" if diff else "old"
        self.built.append(diff)
        try:
            if self.fail_in == "build":
                raise PatchError("diff does not apply")
            yield Replica(base_url=f"http://{name}.replica:3001", source_dir=str(self.root / name))
        finally:
            self.torn_down.append(name)

    def client(self):
        def handler(request):
            return httpx.Response(self.status[request.url.host.split(".")[0]], text="body")

        return httpx.Client(transport=httpx.MockTransport(handler))

    def semgrep(self, config, paths, *, cwd):
        self.semgrep_calls.append((Path(config).read_text(), paths, cwd))
        if self.fail_in == "semgrep":
            raise RuntimeError("semgrep exited with code 2")
        return {"findings": self.findings[Path(cwd).name], "results": []}

    def smoke(self, client, base_url):
        return {"passed": 6 - self.reg_failed, "failed": self.reg_failed, "failures": []}

    def manager(self, **kw):
        kw.setdefault("validate", lambda path: None)
        return SandboxManager(Settings(production_source_root=str(self.root / "old")),
                              builder=self.builder, client=self.client(),
                              semgrep=self.semgrep, smoke=self.smoke, **kw)


def test_verify_passes_when_blocked_after_and_rule_clean():
    h = Harness()
    r = h.manager().verify_patch(DIFF, "rules: []", REPRO)
    assert r["passed"] is True and r["hash"] == diff_hash(DIFF)
    assert r["exploit_before"] == 200 and r["exploit_after"] == 401
    assert r["semgrep_old"] == 2 and r["semgrep_new"] == 0
    assert r["regression"]["failed"] == 0
    assert r["replica_before"] == {"status": 200, "excerpt": "body"}


def test_verify_builds_unpatched_then_patched_and_tears_both_down():
    h = Harness()
    h.manager().verify_patch(DIFF, "rules: []", REPRO)
    assert h.built == ["", DIFF]
    assert h.torn_down == ["old", "new"]


def test_verify_runs_the_rule_on_the_touched_files_of_each_tree():
    h = Harness()
    h.manager().verify_patch(DIFF, "rules: [x]", REPRO)
    assert h.semgrep_calls == [("rules: [x]\n", ["lib/insecurity.ts"], str(h.root / "old")),
                               ("rules: [x]\n", ["lib/insecurity.ts"], str(h.root / "new"))]


@pytest.mark.parametrize("over", [
    {"after": 200},
    {"before": 401},
    {"semgrep_new": 1},
    {"semgrep_old": 0},
    {"reg_failed": 1},
])
def test_verify_fails_unless_every_check_holds(over):
    assert Harness(**over).manager().verify_patch(DIFF, "y", REPRO)["passed"] is False


def test_a_rule_semgrep_cannot_run_is_a_patch_error_after_teardown():
    h = Harness(fail_in="semgrep")
    with pytest.raises(PatchError, match="rule could not run: semgrep exited with code 2"):
        h.manager().verify_patch(DIFF, "y", REPRO)
    assert h.torn_down == ["old"]


def test_a_replay_transport_failure_is_a_sandbox_error():
    h = Harness()

    def handler(request):
        raise httpx.ReadTimeout("timed out")

    mgr = SandboxManager(Settings(), builder=h.builder, semgrep=h.semgrep, smoke=h.smoke,
                         validate=lambda path: None,
                         client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(SandboxError, match="replay on the replica failed"):
        mgr.reproduce(REPRO)
    assert h.torn_down == ["old"]


def test_replica_is_torn_down_when_a_check_raises():
    h = Harness()
    mgr = h.manager()

    def broken_smoke(client, base_url):
        raise httpx.ConnectError("replica went away")

    mgr._smoke = broken_smoke
    with pytest.raises(httpx.ConnectError):
        mgr.verify_patch(DIFF, "y", REPRO)
    assert h.torn_down == ["old", "new"]


def test_patch_errors_propagate_after_teardown():
    h = Harness(fail_in="build")
    with pytest.raises(PatchError):
        h.manager().verify_patch(DIFF, "y", REPRO)
    assert h.torn_down == ["old"]


def test_reproduce_replays_on_an_unpatched_replica():
    h = Harness()
    assert h.manager().reproduce(REPRO) == {"status": 200, "excerpt": "body"}
    assert h.built == [""] and h.torn_down == ["old"]


def test_a_second_caller_is_refused_while_a_replica_runs():
    h = Harness()
    mgr = h.manager(lock_timeout_s=0)
    entered, release = threading.Event(), threading.Event()
    original = h.builder

    @contextmanager
    def slow_builder(diff):
        with original(diff) as replica:
            entered.set()
            release.wait(5)
            yield replica

    mgr._builder = slow_builder
    worker = threading.Thread(target=mgr.reproduce, args=(REPRO,))
    worker.start()
    entered.wait(5)
    with pytest.raises(SandboxBusy):
        mgr.reproduce(REPRO)
    release.set()
    worker.join(5)
    assert mgr.reproduce(REPRO)["status"] == 200


def test_touched_files_reads_both_sides_of_the_diff():
    diff = DIFF + "--- /dev/null\n+++ b/routes/new.ts\n@@ -0,0 +1 @@\n+x\n"
    assert touched_files(diff) == ["lib/insecurity.ts", "routes/new.ts"]


def test_scan_counts_zero_without_calling_semgrep_when_no_touched_file_exists(tmp_path):
    h = Harness()
    assert h.manager()._scan("rule.yaml", ["lib/missing.ts"], str(tmp_path)) == 0
    assert h.semgrep_calls == []


@pytest.mark.parametrize("diff", ["", "not a diff", "--- a/../x\n+++ b/../x\n", "+++ b//etc/x\n"])
def test_touched_files_refuses_empty_or_escaping_diffs(diff):
    with pytest.raises(PatchError):
        touched_files(diff)


def test_verify_builds_the_normalized_diff_but_hashes_the_agents_diff():
    h = Harness()
    (h.root / "old" / "lib" / "insecurity.ts").write_text("a\nx\nb\n")
    bare = "```diff\n--- lib/insecurity.ts\n+++ lib/insecurity.ts\n@@\n-x\n+y\n```\n"
    r = h.manager().verify_patch(bare, "rules: []", REPRO)
    assert r["hash"] == diff_hash(bare)
    assert h.built[1] == r["applied_diff"]
    assert r["applied_diff"].startswith("--- a/lib/insecurity.ts\n+++ b/lib/insecurity.ts\n@@ -1,3 +1,3 @@\n")


def test_an_invalid_rule_is_refused_with_semgreps_message_before_any_replica():
    h = Harness()
    with pytest.raises(PatchError, match="rule is invalid: mapping values are not allowed"):
        h.manager(validate=lambda path: "mapping values are not allowed").verify_patch(DIFF, "y", REPRO)
    assert h.built == []


def test_the_rule_is_written_without_fences():
    h = Harness()
    h.manager().verify_patch(DIFF, "```yaml\nrules: [x]\n```", REPRO)
    assert h.semgrep_calls[0][0] == "rules: [x]\n"
