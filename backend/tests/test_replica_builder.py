import os
import time
from pathlib import Path

import pytest

from rootlane_toolbox.core.config import Settings
from rootlane_toolbox.integrations.sandbox import (
    PatchError,
    ReplicaBuilder,
    SandboxError,
    run_process,
    spawn_process,
    stop_process,
)


class FakeProc:
    def __init__(self, exit_code=None):
        self.exit_code = exit_code

    def poll(self):
        return self.exit_code


class Fakes:
    def __init__(self, tmp_path, *, run_results=None, exit_code=None, ready_after=0, port_free=True):
        self.source = tmp_path / "prod"
        (self.source / "lib").mkdir(parents=True)
        (self.source / "lib" / "insecurity.ts").write_text("old\n")
        (self.source / "node_modules" / "jws").mkdir(parents=True)
        (self.source / "frontend" / "node_modules" / "x").mkdir(parents=True)
        (self.source / "frontend" / "dist").mkdir(parents=True)
        (self.source / ".git").mkdir()
        self.work = tmp_path / "work"
        self.work.mkdir()
        self.run_results = list(run_results or [])
        self.exit_code = exit_code
        self.ready_after = ready_after
        self.port_free = port_free
        self.runs, self.spawned, self.stopped, self.probes = [], [], [], 0

    def run(self, args, *, cwd, input, timeout, env=None):
        self.runs.append((args, cwd, input, timeout))
        result = self.run_results.pop(0) if self.run_results else (0, "")
        if isinstance(result, Exception):
            raise result
        return result

    def spawn(self, args, *, cwd, env, log_path):
        self.spawned.append((args, cwd, env))
        Path(log_path).write_text("Error: ENOENT frontend/dist/frontend/index.html\n")
        return FakeProc(self.exit_code)

    def stop(self, proc):
        self.stopped.append(proc)

    def probe(self, base_url):
        self.probes += 1
        return self.probes > self.ready_after

    def builder(self, **settings):
        values = {"production_source_root": str(self.source), "sandbox_port": 3999,
                  "sandbox_build_timeout_s": 60, "sandbox_start_timeout_s": 1}
        values.update(settings)
        return ReplicaBuilder(
            Settings(**values), run=self.run, spawn=self.spawn, stop=self.stop, probe=self.probe,
            port_free=lambda port: self.port_free, sleep=lambda s: None, workdir=str(self.work),
        )


def _leftovers(fakes):
    return list(fakes.work.iterdir())


def test_unpatched_replica_copies_source_links_deps_and_starts_node(tmp_path):
    f = Fakes(tmp_path)
    with f.builder().build("") as replica:
        src = Path(replica.source_dir)
        assert replica.base_url == "http://127.0.0.1:3999"
        assert (src / "lib" / "insecurity.ts").read_text() == "old\n"
        assert (src / "node_modules").is_symlink()
        assert os.readlink(src / "node_modules") == str(f.source / "node_modules")
        assert not (src / ".git").exists()
        assert not (src / "frontend" / "node_modules").exists()
        assert (src / "frontend" / "dist").is_dir()
    assert f.runs == []
    args, cwd, env = f.spawned[0]
    assert args == ["node", "build/app.js"] and cwd == str(src) and env["PORT"] == "3999"
    assert len(f.stopped) == 1 and _leftovers(f) == []


def test_patched_replica_applies_the_diff_and_rebuilds_the_server(tmp_path):
    f = Fakes(tmp_path)
    with f.builder().build("the diff") as replica:
        pass
    (apply_args, cwd, stdin, timeout), (build_args, _, _, _) = f.runs
    assert apply_args[:2] == ["git", "apply"] and stdin == "the diff" and timeout == 60
    assert cwd == replica.source_dir
    assert build_args == ["node_modules/.bin/tsc"]
    assert len(f.stopped) == 1 and _leftovers(f) == []


def test_replica_and_build_get_a_minimal_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TOOLBOX_API_KEY", "do-not-leak")
    f = Fakes(tmp_path)
    seen = []
    f_run = f.run

    def run(args, *, cwd, input, timeout, env):
        seen.append(env)
        return f_run(args, cwd=cwd, input=input, timeout=timeout)

    f.run = run
    with f.builder().build("diff"):
        pass
    env = f.spawned[0][2]
    assert set(env) <= {"PATH", "HOME", "PORT"} and env["PORT"] == "3999"
    assert all("TOOLBOX_API_KEY" not in e for e in seen) and len(seen) == 2


def test_diff_that_does_not_apply_is_a_patch_error_and_cleans_up(tmp_path):
    f = Fakes(tmp_path, run_results=[(1, "error: patch failed: lib/insecurity.ts:1")])
    with pytest.raises(PatchError, match="patch failed"):
        with f.builder().build("bad"):
            pass
    assert f.spawned == [] and _leftovers(f) == []


def test_build_failure_is_a_patch_error_with_the_compiler_output(tmp_path):
    f = Fakes(tmp_path, run_results=[(0, ""), (2, "lib/insecurity.ts(3,1): error TS1005")])
    with pytest.raises(PatchError, match="TS1005"):
        with f.builder().build("diff"):
            pass
    assert f.spawned == [] and _leftovers(f) == []


def test_build_timeout_cleans_up(tmp_path):
    f = Fakes(tmp_path, run_results=[(0, ""), SandboxError("timed out after 60s")])
    with pytest.raises(SandboxError, match="timed out"):
        with f.builder().build("diff"):
            pass
    assert f.spawned == [] and _leftovers(f) == []


def test_replica_that_exits_during_startup_is_stopped_and_removed(tmp_path):
    f = Fakes(tmp_path, exit_code=1, ready_after=10**6)
    with pytest.raises(SandboxError, match="exited.*ENOENT frontend/dist"):
        with f.builder().build(""):
            pass
    assert len(f.stopped) == 1 and _leftovers(f) == []


def test_replica_that_never_gets_ready_times_out_and_is_stopped(tmp_path):
    f = Fakes(tmp_path, ready_after=10**6)
    with pytest.raises(SandboxError, match="not ready"):
        with f.builder(sandbox_start_timeout_s=0).build(""):
            pass
    assert len(f.stopped) == 1 and _leftovers(f) == []


def test_replica_is_stopped_and_removed_when_the_caller_fails(tmp_path):
    f = Fakes(tmp_path)
    with pytest.raises(RuntimeError):
        with f.builder().build(""):
            raise RuntimeError("check failed")
    assert len(f.stopped) == 1 and _leftovers(f) == []


def test_run_process_returns_code_and_output(tmp_path):
    assert run_process(["cat"], cwd=str(tmp_path), input="hi", timeout=5) == (0, "hi")


def test_run_process_kills_on_timeout(tmp_path):
    with pytest.raises(SandboxError, match="timed out"):
        run_process(["sleep", "5"], cwd=str(tmp_path), input=None, timeout=0.2)


def test_stop_process_ends_a_spawned_process(tmp_path):
    log = tmp_path / "replica.log"
    proc = spawn_process(["sh", "-c", "echo started; sleep 30"], cwd=str(tmp_path),
                         env={"PATH": os.environ["PATH"]}, log_path=str(log))
    time.sleep(0.2)
    stop_process(proc)
    assert proc.poll() is not None and log.read_text() == "started\n"


def test_busy_port_is_refused_before_anything_starts(tmp_path):
    f = Fakes(tmp_path, port_free=False)
    with pytest.raises(SandboxError, match="port"):
        with f.builder().build(""):
            pass
    assert f.spawned == [] and _leftovers(f) == []
