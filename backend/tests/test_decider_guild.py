import json

import httpx
import pytest

from rootlane_toolbox.core.config import Settings
from rootlane_toolbox.analysis.decider import AkashMLDecider, TriageError
from rootlane_toolbox.integrations.guild import GuildTrigger


def _decider(content, status=200):
    seen = {}

    def handler(request):
        seen["req"] = request
        return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})

    settings = Settings(triage_api_key="k", triage_base_url="https://x.test/v1", triage_model="m1")
    http = httpx.Client(
        base_url=settings.triage_base_url,
        headers={"Authorization": "Bearer k"},
        transport=httpx.MockTransport(handler),
    )
    return AkashMLDecider(settings, http=http), seen


def test_decider_posts_chat_completion_and_parses_verdict():
    d, seen = _decider('Sure: {"verdict": "escalate", "rationale": "burst"} done')
    out = d.decide({"principals": []})
    assert out == {"verdict": "escalate", "rationale": "burst", "model": "m1"}
    req = seen["req"]
    assert req.url.path == "/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer k"
    assert json.loads(req.content)["model"] == "m1"


def _failing_decider(exc=None, status=200, content="x"):
    def handler(request):
        if exc:
            raise exc
        return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})

    settings = Settings(triage_api_key="k", triage_base_url="https://x.test/v1")
    http = httpx.Client(base_url=settings.triage_base_url, transport=httpx.MockTransport(handler))
    return AkashMLDecider(settings, http=http)


@pytest.mark.parametrize(
    "decider,reason",
    [
        (_failing_decider(exc=httpx.ReadTimeout("t")), "triage timed out"),
        (_failing_decider(exc=httpx.ConnectTimeout("t")), "triage timed out"),
        (_failing_decider(exc=httpx.ConnectError("c")), "triage connection failed"),
        (_failing_decider(status=401), "triage http 401"),
        (_failing_decider(content="no json"), "triage returned no verdict"),
        (_failing_decider(content='{"verdict": "panic"}'), "triage returned no verdict"),
    ],
)
def test_decider_failures_raise_a_reasoned_triage_error(decider, reason):
    with pytest.raises(TriageError) as err:
        decider.decide({})
    assert str(err.value) == reason


def test_decider_client_timeout_comes_from_settings():
    d = AkashMLDecider(Settings(triage_api_key="k", triage_timeout_s=45))
    assert d._http.timeout.read == 45 and d._http.timeout.connect == 45


def _guild(settings, status=201):
    seen = {}

    def handler(request):
        seen["req"] = request
        return httpx.Response(status, json={"id": "gs_1"})

    http = httpx.Client(base_url="https://api.guild.ai", transport=httpx.MockTransport(handler))
    return GuildTrigger(settings, http=http), seen


def test_guild_returns_none_without_trigger_env():
    g, seen = _guild(Settings())
    assert g.start_session({"id": "inc_1"}) is None
    assert "req" not in seen


def test_guild_posts_api_trigger_with_basic_auth():
    s = Settings(guild_workspace="own/ws", guild_trigger_key_id="kid", guild_trigger_secret="sec")
    g, seen = _guild(s)
    assert g.start_session({"id": "inc_1"}) == "gs_1"
    req = seen["req"]
    assert req.url.path == "/v1/workspaces/own/ws/sessions"
    assert req.headers["authorization"].startswith("Basic ")
    assert json.loads(req.content) == {
        "session_type": "api_trigger",
        "agent_input": {"incident_id": "inc_1"},
    }


def test_guild_failed_call_returns_none():
    s = Settings(guild_workspace="own/ws", guild_trigger_key_id="kid", guild_trigger_secret="sec")
    g, _ = _guild(s, status=500)
    assert g.start_session({"id": "inc_1"}) is None
