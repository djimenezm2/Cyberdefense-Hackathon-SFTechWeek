import secrets
from collections.abc import Callable

import httpx


class CheckFailed(Exception):
    """Raised by a smoke check whose response is not the expected one."""


def _expect(response: httpx.Response, status: int) -> httpx.Response:
    if response.status_code != status:
        raise CheckFailed(f"{response.request.method} {response.request.url.path} -> {response.status_code}")
    return response


def _token(ctx: dict) -> str:
    if "token" not in ctx:
        raise CheckFailed("no session token")
    return ctx["token"]


def _register(client: httpx.Client, base: str, ctx: dict) -> None:
    ctx["email"] = f"rootlane-smoke-{secrets.token_hex(4)}@example.test"
    ctx["password"] = secrets.token_hex(12)
    body = {"email": ctx["email"], "password": ctx["password"], "passwordRepeat": ctx["password"]}
    _expect(client.post(f"{base}/api/Users", json=body), 201)


def _login(client: httpx.Client, base: str, ctx: dict) -> None:
    body = {"email": ctx.get("email"), "password": ctx.get("password")}
    auth = _expect(client.post(f"{base}/rest/user/login", json=body), 200).json()["authentication"]
    ctx["token"], ctx["bid"] = auth["token"], auth["bid"]


def _product_search(client: httpx.Client, base: str, ctx: dict) -> None:
    data = _expect(client.get(f"{base}/rest/products/search", params={"q": "apple"}), 200).json()
    if not isinstance(data.get("data"), list):
        raise CheckFailed("search returned no product list")


def _profile(client: httpx.Client, base: str, ctx: dict) -> None:
    headers = {"Cookie": f"token={_token(ctx)}"}
    user = _expect(client.get(f"{base}/rest/user/whoami", headers=headers), 200).json()["user"]
    if user.get("email") != ctx["email"]:
        raise CheckFailed("profile does not resolve the logged-in user")


def _basket_view(client: httpx.Client, base: str, ctx: dict) -> None:
    headers = {"Authorization": f"Bearer {_token(ctx)}"}
    _expect(client.get(f"{base}/rest/basket/{ctx['bid']}", headers=headers), 200)


def _basket_add(client: httpx.Client, base: str, ctx: dict) -> None:
    headers = {"Authorization": f"Bearer {_token(ctx)}"}
    body = {"ProductId": 1, "BasketId": ctx["bid"], "quantity": 1}
    _expect(client.post(f"{base}/api/BasketItems", json=body, headers=headers), 200)


CHECKS: list[tuple[str, Callable[[httpx.Client, str, dict], None]]] = [
    ("register", _register),
    ("login", _login),
    ("product_search", _product_search),
    ("profile", _profile),
    ("basket_view", _basket_view),
    ("basket_add", _basket_add),
]


def run_smoke(client: httpx.Client, base_url: str) -> dict:
    """
    Run the regression smoke suite against a replica with a freshly registered user.

    Args:
        client (httpx.Client): HTTP client with bounded timeouts.
        base_url (str): The replica origin.

    Returns:
        dict: `{"passed": int, "failed": int, "failures": list[str]}` naming each failed check.
    """
    ctx: dict = {}
    failures = []
    for name, check in CHECKS:
        try:
            check(client, base_url, ctx)
        except (CheckFailed, httpx.HTTPError, ValueError, KeyError, TypeError):
            failures.append(name)
    return {"passed": len(CHECKS) - len(failures), "failed": len(failures), "failures": failures}
