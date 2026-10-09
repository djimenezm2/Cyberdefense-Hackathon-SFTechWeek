"""
Deploy the toolbox to Akash through the Akash Console API.

Usage:
    python deploy.py create [--sdl bootstrap|image] [--tag SHA] [--env-file PATH] [--dry-run]
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
USER_AGENT = "rootlane-deploy/1.0"
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
REQUIRED = (
    "CLICKHOUSE_HOST",
    "CLICKHOUSE_USER",
    "CLICKHOUSE_PASSWORD",
    "CLICKHOUSE_RO_PASSWORD",
    "TOOLBOX_API_KEY",
    "ADMIN_TOKEN",
    "INGEST_TOKEN",
    "TRIAGE_API_KEY",
)
ALLOWED = (
    *REQUIRED,
    "CLICKHOUSE_RO_USER",
    "CLICKHOUSE_DATABASE",
    "CORS_ORIGINS",
    "TRIAGE_BASE_URL",
    "TRIAGE_MODEL",
    "TRIAGE_TIMEOUT_S",
    "ESCALATE_LOGIN_LOOKBACK_S",
    "ANALYZE_INTERVAL_S",
    "GUILD_WORKSPACE",
    "GUILD_TRIGGER_KEY_ID",
    "GUILD_TRIGGER_SECRET",
    "GITHUB_TOKEN",
    "JUICE_SHOP_REPO",
)

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
    Build the container env from the local .env values, limited to the allowlist.

    Args:
        dotenv (dict[str, str]): Values read from the .env file.

    Returns:
        dict[str, str]: Allowlisted, non-empty values with defaults applied and the triage key mapped.

    Raises:
        ValueError: If a required name has no value; the message lists names only.
    """
    merged = {**DEFAULTS, **{k: v for k, v in dotenv.items() if v}}
    if not merged.get("TRIAGE_API_KEY") and merged.get("AKASHML_API_KEY"):
        merged["TRIAGE_API_KEY"] = merged["AKASHML_API_KEY"]
    missing = [name for name in REQUIRED if not merged.get(name)]
    if missing:
        raise ValueError(f"missing required deploy vars: {', '.join(missing)}")
    return {name: merged[name] for name in ALLOWED if merged.get(name)}


def sent_env_names(sdl: str) -> list[str]:
    """List the env var names a rendered SDL carries, without their values."""
    return re.findall(r'^\s*- "([A-Z0-9_]+)=', sdl, flags=re.MULTILINE)


def error_message(code: int, body: bytes) -> str:
    """
    Summarize an HTTP error without echoing the response body.

    Args:
        code (int): The HTTP status code.
        body (bytes): The raw response body.

    Returns:
        str: `<code>: <message or error field> (code <api code>)`, the field cut to 300 characters;
            for a non-JSON body only an edge `error code: <n>` line is kept.
    """
    try:
        payload = json.loads(body)
    except ValueError:
        edge = re.fullmatch(rb"\s*(error code: \d+)\s*", body)
        return f"{code}: {edge.group(1).decode() if edge else ''}"
    if not isinstance(payload, dict):
        return f"{code}: "
    detail = str(payload.get("message") or payload.get("error") or "")[:300]
    api_code = payload.get("code")
    return f"{code}: {detail} (code {str(api_code)[:80]})" if api_code else f"{code}: {detail}"


def build_request(method: str, path: str, key: str, body: dict | None = None) -> urllib.request.Request:
    """Build a Console API request; the edge rejects urllib's default User-Agent with error 1010."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API + path, data=data, method=method)
    request.add_header("x-api-key", key)
    request.add_header("content-type", "application/json")
    request.add_header("user-agent", USER_AGENT)
    return request


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
    request = build_request(method, path, key, body)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        sys.exit(f"{method} {path} -> {error_message(error.code, error.read())}")


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
    parser.add_argument("--dry-run", action="store_true", help="print the env names and target, send nothing")
    args = parser.parse_args()

    dotenv = read_dotenv(args.env_file) if args.env_file.exists() else {}
    if args.command != "status":
        try:
            sdl = render_sdl(SDLS[args.sdl].read_text(), deploy_env(dotenv), image_tag=args.tag)
        except ValueError as error:
            sys.exit(str(error))
        if args.dry_run:
            print("target", API, "command", args.command, "sdl", SDLS[args.sdl].name)
            print("env names", " ".join(sent_env_names(sdl)))
            return
    key = os.environ.get("AKASH_CONSOLE_API_KEY") or dotenv.get("AKASH_CONSOLE_API_KEY")
    if not key:
        sys.exit("AKASH_CONSOLE_API_KEY is not set")
    if args.command == "status":
        status(key)
    elif args.command == "create":
        create(key, sdl)
    else:
        update(key, sdl)


if __name__ == "__main__":
    main()
