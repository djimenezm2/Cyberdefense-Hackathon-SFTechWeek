import json

import httpx

from rootlane_toolbox.config import Settings
from rootlane_toolbox.decider import AkashMLDecider
from rootlane_toolbox.guild import GuildTrigger


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


def test_decider_unparseable_or_unknown_verdict_becomes_watch():
    assert _decider("no json")[0].decide({})["verdict"] == "watch"
    assert _decider('{"verdict": "panic"}')[0].decide({})["verdict"] == "watch"


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
