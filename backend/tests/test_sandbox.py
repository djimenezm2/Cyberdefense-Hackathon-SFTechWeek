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
        return SandboxManager(Settings(), builder=self.builder, client=self.client(),
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
    assert h.semgrep_calls == [("rules: [x]", ["lib/insecurity.ts"], str(h.root / "old")),
                               ("rules: [x]", ["lib/insecurity.ts"], str(h.root / "new"))]


@pytest.mark.parametrize("over", [
    {"after": 200},
    {"before": 401},
    {"semgrep_new": 1},
    {"semgrep_old": 0},
    {"reg_failed": 1},
])
def test_verify_fails_unless_every_check_holds(over):
    assert Harness(**over).manager().verify_patch(DIFF, "y", REPRO)["passed"] is False


def test_replica_is_torn_down_when_a_check_raises():
    h = Harness(fail_in="semgrep")
    with pytest.raises(RuntimeError):
        h.manager().verify_patch(DIFF, "y", REPRO)
    assert h.torn_down == ["old"]


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
