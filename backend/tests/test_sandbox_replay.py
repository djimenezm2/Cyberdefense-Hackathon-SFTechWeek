import httpx
import pytest

from rootlane_toolbox.core.guards import GuardError
from rootlane_toolbox.integrations.sandbox import parse_reproduction, replay

BASE = "http://127.0.0.1:3001"


def _repro(**over):
    data = {"method": "GET", "path": "/rest/basket/2", "headers": {}, "body": None,
            "expected_blocked_status": 401}
    data.update(over)
    return data


def _client(seen, status=200, text="ok"):
    def handler(request):
        seen.append(request)
        return httpx.Response(status, text=text)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_accepts_a_plain_request():
    repro = parse_reproduction(_repro(method="post", body={"q": 1}))
    assert repro.method == "POST" and repro.expected_blocked_status == 401


@pytest.mark.parametrize("path", [
    "rest/basket/2",
    "//evil.example/x",
    "http://evil.example/x",
    "https://evil.example/",
    "/\\evil.example",
    "/a b",
    "/a\r\nHost: x",
    "",
])
def test_parse_refuses_paths_that_could_leave_the_replica(path):
    with pytest.raises(GuardError):
        parse_reproduction(_repro(path=path))


def test_parse_keeps_absolute_urls_inside_the_query():
    repro = parse_reproduction(_repro(path="/redirect?to=https://github.com/x"))
    assert repro.path == "/redirect?to=https://github.com/x"


@pytest.mark.parametrize("over", [
    {"method": "CONNECT"},
    {"method": "TRACE"},
    {"expected_blocked_status": 200},
    {"expected_blocked_status": 500},
    {"headers": {"Bad Name": "x"}},
    {"headers": {"X-A": "v\r\nInjected: 1"}},
    {"path": 7},
])
def test_parse_refuses_invalid_fields(over):
    with pytest.raises(GuardError):
        parse_reproduction(_repro(**over))


def test_parse_drops_host_and_hop_by_hop_headers():
    headers = {"Host": "evil.example", "Authorization": "Bearer t", "Content-Length": "9",
               "Transfer-Encoding": "chunked", "Connection": "close", "X-Forwarded-Host": "e"}
    repro = parse_reproduction(_repro(headers=headers))
    assert repro.headers == {"Authorization": "Bearer t", "X-Forwarded-Host": "e"}


def test_replay_sends_the_request_to_the_replica_only():
    seen = []
    repro = parse_reproduction(_repro(headers={"Host": "evil.example", "Authorization": "Bearer t"}))
    out = replay(_client(seen, 200, "x" * 2000), BASE, repro)
    request = seen[0]
    assert str(request.url) == "http://127.0.0.1:3001/rest/basket/2"
    assert request.headers["host"] == "127.0.0.1:3001"
    assert request.headers["authorization"] == "Bearer t"
    assert out["status"] == 200 and len(out["excerpt"]) == 500


def test_replay_sends_json_and_text_bodies():
    seen = []
    client = _client(seen)
    replay(client, BASE, parse_reproduction(_repro(method="POST", body={"email": "a"})))
    replay(client, BASE, parse_reproduction(_repro(method="POST", body="raw=1")))
    assert seen[0].content == b'{"email":"a"}'
    assert seen[0].headers["content-type"] == "application/json"
    assert seen[1].content == b"raw=1"


def test_replay_does_not_follow_redirects():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example/"})

    out = replay(httpx.Client(transport=httpx.MockTransport(handler)), BASE,
                 parse_reproduction(_repro()))
    assert out["status"] == 302 and len(seen) == 1
