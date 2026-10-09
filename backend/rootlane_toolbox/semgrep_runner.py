import json
import subprocess
from collections.abc import Callable, Sequence

DEFAULT_CONFIG = "rules/"
Runner = Callable[[list[str], str], tuple[int, str]]


def _subprocess_runner(args: list[str], cwd: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"semgrep could not run: {exc}") from exc
    return proc.returncode, proc.stdout


def run_semgrep(
    config: str | None,
    paths: Sequence[str] | None,
    *,
    runner: Runner = _subprocess_runner,
    cwd: str = ".",
) -> dict:
    """
    Run the Semgrep CLI and summarise its JSON output.

    Args:
        config (str | None): Rule file, directory or registry id; defaults to `rules/`.
        paths (Sequence[str] | None): Targets relative to cwd; defaults to `.`.
        runner (Runner): Executes the command and returns (exit code, stdout).
        cwd (str): Directory the scan runs in.

    Returns:
        dict: `{"findings": int, "results": list}` from Semgrep's `results`.

    Raises:
        RuntimeError: If Semgrep exits with an error or prints invalid JSON.
    """
    args = ["semgrep", "--json", "--quiet", "--config", config or DEFAULT_CONFIG, *(paths or ["."])]
    code, stdout = runner(args, cwd)
    if code not in (0, 1):
        raise RuntimeError(f"semgrep exited with code {code}")
    try:
        results = json.loads(stdout).get("results", [])
    except json.JSONDecodeError as exc:
        raise RuntimeError("semgrep produced invalid JSON") from exc
    return {"findings": len(results), "results": results}
