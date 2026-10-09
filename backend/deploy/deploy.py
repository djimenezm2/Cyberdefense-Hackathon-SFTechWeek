"""
Deploy the toolbox to Akash through the Akash Console API.

Usage:
    python deploy.py create [--sdl bootstrap|image] [--tag SHA] [--env-file PATH]
    python deploy.py update [--sdl bootstrap|image] [--tag SHA] [--env-file PATH]
    python deploy.py status

The Console API key is read from `AKASH_CONSOLE_API_KEY` (environment, else the env file).
The deployment id and provider are kept in `.state.json` next to this script.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://console-api.akash.network"
HERE = Path(__file__).resolve().parent
STATE = HERE / ".state.json"
SDLS = {"bootstrap": HERE / "akash.bootstrap.sdl.yaml", "image": HERE / "akash.sdl.yaml"}
PLACEHOLDER = "__SET_AT_DEPLOY__"
DEFAULTS = {
    "TRIAGE_BASE_URL": "https://api.akashml.com/v1",
    "TRIAGE_MODEL": "zai-org/GLM-5.3",
    "CORS_ORIGINS": "https://app.rootlane.xyz",
    "ANALYZE_INTERVAL_S": "10",
}

_ENV_LINE = re.compile(rf"^(\s*)- ([A-Z0-9_]+)={PLACEHOLDER}\s*$")
_IMAGE_LINE = re.compile(r"^(\s*image:\s*\S+?):[^:\s/]+\s*$")


def render_sdl(template: str, env: dict[str, str], image_tag: str | None = None) -> str:
    """
    Fill the SDL's placeholder env entries and optionally pin the image tag.

    Args:
        template (str): SDL text whose env entries read `- NAME=__SET_AT_DEPLOY__`.
        env (dict[str, str]): Values by name; names absent or empty are dropped from the SDL.
        image_tag (str | None): Tag that replaces the image's current tag, when given.

    Returns:
        str: The rendered SDL.

    Raises:
        ValueError: If a placeholder is left after rendering.
    """
    lines = []
    for line in template.splitlines():
        match = _ENV_LINE.match(line)
        if match:
            indent, name = match.groups()
            if env.get(name):
                lines.append(f"{indent}- {json.dumps(f'{name}={env[name]}')}")
            continue
        if image_tag:
            line = _IMAGE_LINE.sub(rf"\1:{image_tag}", line)
        lines.append(line)
    rendered = "\n".join(lines) + "\n"
    if PLACEHOLDER in rendered:
        raise ValueError("SDL still contains a deploy-time placeholder")
    return rendered


def deploy_env(dotenv: dict[str, str]) -> dict[str, str]:
    """
    Build the deploy-time env from the local .env values.

    Args:
        dotenv (dict[str, str]): Values read from the .env file.

    Returns:
        dict[str, str]: The values with defaults applied and the triage key mapped.
    """
    env = {**DEFAULTS, **{k: v for k, v in dotenv.items() if v}}
    if not env.get("TRIAGE_API_KEY") and env.get("AKASHML_API_KEY"):
        env["TRIAGE_API_KEY"] = env["AKASHML_API_KEY"]
    return env


def cheapest_bid(bids: list[dict]) -> dict | None:
    """
    Pick the open bid with the lowest price.

    Args:
        bids (list[dict]): Items of the Console API `GET /v1/bids` response.

    Returns:
        dict | None: The chosen `bid` object, None when no bid is open.
    """
    open_bids = [b["bid"] for b in bids if b["bid"].get("state") == "open"]
    return min(open_bids, key=lambda b: float(b["price"]["amount"]), default=None)


def read_dotenv(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines, ignoring comments and surrounding quotes."""
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def call(method: str, path: str, key: str, body: dict | None = None) -> dict:
    """Send one Console API request and return the decoded JSON body."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API + path, data=data, method=method)
    request.add_header("x-api-key", key)
    request.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        sys.exit(f"{method} {path} -> {error.code}: {error.read().decode()[:2000]}")


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def summarize(deployment: dict) -> None:
    """Print the deployment state and each lease's service URIs."""
    data = deployment["data"]
    print("deployment", data["deployment"]["id"]["dseq"], data["deployment"]["state"])
    for lease in data["leases"]:
        print("lease", lease["id"]["provider"], lease["state"], lease["price"])
        status = lease.get("status") or {}
        for name, service in (status.get("services") or {}).items():
            print("service", name, json.dumps(service))
        if status.get("forwarded_ports"):
            print("forwarded_ports", json.dumps(status["forwarded_ports"]))


def create(key: str, sdl: str) -> None:
    created = call("POST", "/v1/deployments", key, {"data": {"sdl": sdl}})["data"]
    dseq = created["dseq"]
    save_state({"dseq": dseq})
    print("dseq", dseq)
    bid = None
    for _ in range(30):
        time.sleep(6)
        bid = cheapest_bid(call("GET", f"/v1/bids?dseq={dseq}", key)["data"])
        if bid:
            break
    if not bid:
        sys.exit(f"no open bid for dseq {dseq}")
    bid_id = bid["id"]
    print("bid", bid_id["provider"], bid["price"])
    lease = {"dseq": dseq, "gseq": bid_id["gseq"], "oseq": bid_id["oseq"], "provider": bid_id["provider"]}
    result = call("POST", "/v1/leases", key, {"leases": [lease]})
    save_state({"dseq": dseq, "provider": bid_id["provider"], "price": bid["price"]})
    summarize(result)


def update(key: str, sdl: str) -> None:
    dseq = load_state()["dseq"]
    summarize(call("PUT", f"/v1/deployments/{dseq}", key, {"data": {"sdl": sdl}}))


def status(key: str) -> None:
    summarize(call("GET", f"/v1/deployments/{load_state()['dseq']}", key))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["create", "update", "status"])
    parser.add_argument("--sdl", choices=sorted(SDLS), default="bootstrap")
    parser.add_argument("--tag", help="image tag for the image SDL")
    parser.add_argument("--env-file", type=Path, default=HERE.parents[1] / ".env")
    args = parser.parse_args()

    dotenv = read_dotenv(args.env_file) if args.env_file.exists() else {}
    key = os.environ.get("AKASH_CONSOLE_API_KEY") or dotenv.get("AKASH_CONSOLE_API_KEY")
    if not key:
        sys.exit("AKASH_CONSOLE_API_KEY is not set")
    if args.command == "status":
        status(key)
        return
    sdl = render_sdl(SDLS[args.sdl].read_text(), deploy_env(dotenv), image_tag=args.tag)
    create(key, sdl) if args.command == "create" else update(key, sdl)


if __name__ == "__main__":
    main()
