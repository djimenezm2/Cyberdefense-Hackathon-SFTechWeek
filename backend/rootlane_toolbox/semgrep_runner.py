import json
import subprocess
from pathlib import Path
from collections.abc import Callable, Sequence

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
DEFAULT_PACK = "p/typescript"
Runner = Callable[[list[str], str], tuple[int, str]]


def _subprocess_runner(args: list[str], cwd: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"semgrep could not run: {exc}") from exc
    return proc.returncode, proc.stdout


def _local_rules(rules_dir: Path) -> list[str]:
    has_rules = rules_dir.is_dir() and any(p.name != ".gitkeep" for p in rules_dir.iterdir())
    return [str(rules_dir)] if has_rules else []


def run_semgrep(
    config: str | None,
    paths: Sequence[str] | None,
    *,
    runner: Runner = _subprocess_runner,
    cwd: str = ".",
    rules_dir: Path = RULES_DIR,
) -> dict:
    """
    Run the Semgrep CLI and summarise its JSON output.

    Args:
        config (str | None): Registry pack or rule file; defaults to the TypeScript pack plus
            the toolbox rules directory when it holds rules.
        paths (Sequence[str] | None): Targets relative to cwd; defaults to `.`.
        runner (Runner): Executes the command and returns (exit code, stdout).
        cwd (str): Directory the scan runs in.
        rules_dir (Path): Toolbox-owned directory of local rules.

    Returns:
        dict: `{"findings": int, "results": list}` from Semgrep's `results`.

    Raises:
        RuntimeError: If Semgrep exits with an error or prints invalid JSON.
    """
    configs = [config] if config else [DEFAULT_PACK, *_local_rules(rules_dir)]
    args = ["semgrep", "--json", "--quiet", "--metrics=off"]
    for entry in configs:
        args += ["--config", entry]
    args += ["--", *(paths or ["."])]
    code, stdout = runner(args, cwd)
    if code not in (0, 1):
        raise RuntimeError(f"semgrep exited with code {code}")
    try:
        results = json.loads(stdout).get("results", [])
    except json.JSONDecodeError as exc:
        raise RuntimeError("semgrep produced invalid JSON") from exc
    return {"findings": len(results), "results": results}
