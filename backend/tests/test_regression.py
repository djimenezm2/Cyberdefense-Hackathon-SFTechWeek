import json

import httpx

from rootlane_toolbox.integrations.regression import CHECKS, run_smoke

BASE = "http://127.0.0.1:3001"


def _shop(broken=()):
    """A minimal stand-in for the replica's API, optionally breaking named routes."""
    state = {}

    def handler(request):
        key = f"{request.method} {request.url.path}"
        if key in broken:
            return httpx.Response(500, text="boom")
        auth = request.headers.get("authorization") == "Bearer tok"
        if key == "POST /api/Users":
            state["email"] = json.loads(request.content)["email"]
            return httpx.Response(201, json={"data": {"id": 30, "email": state["email"]}})
        if key == "POST /rest/user/login":
            body = json.loads(request.content)
            if body["email"] != state.get("email"):
                return httpx.Response(401, text="Invalid email or password.")
            return httpx.Response(200, json={"authentication": {"token": "tok", "bid": 7,
                                                                "umail": body["email"]}})
        if key == "GET /rest/products/search":
            return httpx.Response(200, json={"status": "success", "data": [{"id": 1}]})
        if key == "GET /rest/user/whoami":
            ok = request.headers.get("cookie") == "token=tok"
            return httpx.Response(200, json={"user": {"email": state["email"] if ok else None}})
        if key == "GET /rest/basket/7":
            return httpx.Response(200 if auth else 401, json={"data": {"id": 7, "Products": []}})
        if key == "POST /api/BasketItems":
            return httpx.Response(200 if auth else 401, json={"status": "success"})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_all_checks_pass_on_a_healthy_shop():
    out = run_smoke(_shop(), BASE)
    assert out == {"passed": len(CHECKS), "failed": 0, "failures": []}
    assert len(CHECKS) == 6


def test_a_broken_search_is_counted_and_named():
    out = run_smoke(_shop(broken={"GET /rest/products/search"}), BASE)
    assert out["failed"] == 1 and out["failures"] == ["product_search"]


def test_a_broken_login_fails_every_check_that_needs_the_token():
    out = run_smoke(_shop(broken={"POST /rest/user/login"}), BASE)
    assert out["failures"] == ["login", "profile", "basket_view", "basket_add"]
    assert out["passed"] == 2


def test_transport_errors_count_as_failures():
    def handler(request):
        raise httpx.ConnectError("refused")

    out = run_smoke(httpx.Client(transport=httpx.MockTransport(handler)), BASE)
    assert out["passed"] == 0 and out["failed"] == len(CHECKS)
