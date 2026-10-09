"""
Replay one reproduction request against a base URL.

Usage: uv run python scripts/replay.py <base_url> <request.json>
"""

import json
import sys

import httpx

from rootlane_toolbox.integrations.sandbox import parse_reproduction, replay


def main(argv: list[str], client: httpx.Client | None = None) -> int:
    """
    Print `{"status", "excerpt"}` for the request in the JSON file.

    Args:
        argv (list[str]): Base URL and the path of the request JSON.
        client (httpx.Client | None): HTTP client; a 15-second-timeout client by default.

    Returns:
        int: 0 once the request got a response.
    """
    base_url, request_path = argv
    with open(request_path, encoding="utf-8") as fh:
        reproduction = parse_reproduction(json.load(fh))
    client = client or httpx.Client(timeout=15.0, trust_env=False)
    print(json.dumps(replay(client, base_url.rstrip("/"), reproduction)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
