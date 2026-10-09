"""
Run the regression smoke suite against a base URL.

Usage: uv run python scripts/regression_smoke.py <base_url>
"""

import json
import sys

import httpx

from rootlane_toolbox.integrations.regression import run_smoke


def main(argv: list[str], client: httpx.Client | None = None) -> int:
    """
    Print `{"passed", "failed", "failures"}` for the shop at the base URL.

    Args:
        argv (list[str]): The base URL.
        client (httpx.Client | None): HTTP client; a 15-second-timeout client by default.

    Returns:
        int: 0 when every check passed, 1 otherwise.
    """
    (base_url,) = argv
    client = client or httpx.Client(timeout=15.0, trust_env=False)
    result = run_smoke(client, base_url.rstrip("/"))
    print(json.dumps(result))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
