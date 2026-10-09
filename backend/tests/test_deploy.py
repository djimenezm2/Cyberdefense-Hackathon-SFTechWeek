import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "deploy" / "deploy.py"
_spec = importlib.util.spec_from_file_location("rootlane_deploy", _PATH)
deploy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deploy)

TEMPLATE = """services:
  toolbox:
    image: ghcr.io/example/backend:latest
    env:
      - ALPHA=__SET_AT_DEPLOY__
      - BETA=__SET_AT_DEPLOY__
      - GAMMA=__SET_AT_DEPLOY__
    expose:
      - port: 8000
"""


def test_render_fills_values_as_quoted_scalars():
    out = deploy.render_sdl(TEMPLATE, {"ALPHA": "a: b #c", "BETA": "x", "GAMMA": 'q"z'})
    assert '- "ALPHA=a: b #c"' in out
    assert '- "BETA=x"' in out
    assert '- "GAMMA=q\\"z"' in out


def test_render_drops_vars_without_value():
    out = deploy.render_sdl(TEMPLATE, {"ALPHA": "1", "BETA": ""})
    assert "ALPHA=1" in out
    assert "BETA" not in out
    assert "GAMMA" not in out
    assert "expose:" in out


def test_render_sets_image_tag():
    out = deploy.render_sdl(TEMPLATE, {"ALPHA": "1"}, image_tag="0e3928a")
    assert "image: ghcr.io/example/backend:0e3928a" in out


def test_render_keeps_image_without_tag():
    out = deploy.render_sdl(TEMPLATE, {"ALPHA": "1"})
    assert "image: ghcr.io/example/backend:latest" in out


def test_render_raises_on_leftover_placeholder():
    with pytest.raises(ValueError):
        deploy.render_sdl(TEMPLATE + "      args: [__SET_AT_DEPLOY__]\n", {"ALPHA": "1"})


REQUIRED = {
    "CLICKHOUSE_HOST": "h",
    "CLICKHOUSE_USER": "u",
    "CLICKHOUSE_PASSWORD": "p",
    "CLICKHOUSE_RO_PASSWORD": "rp",
    "TOOLBOX_API_KEY": "tk",
    "ADMIN_TOKEN": "at",
    "INGEST_TOKEN": "it",
    "AKASHML_API_KEY": "k",
}
FORBIDDEN = {"AKASH_CONSOLE_API_KEY": "console-secret-value", "SENSO_API_KEY": "senso-secret-value"}


def test_deploy_env_maps_triage_key_and_defaults():
    env = deploy.deploy_env(REQUIRED)
    assert env["TRIAGE_API_KEY"] == "k"
    assert env["TRIAGE_BASE_URL"] == "https://api.akashml.com/v1"
    assert env["TRIAGE_MODEL"] == "zai-org/GLM-5.3"
    assert env["CORS_ORIGINS"] == "https://app.rootlane.xyz"
    assert env["ANALYZE_INTERVAL_S"] == "10"
    assert env["CLICKHOUSE_HOST"] == "h"


def test_deploy_env_passes_the_optional_triage_timeout():
    assert "TRIAGE_TIMEOUT_S" not in deploy.deploy_env(REQUIRED)
    assert deploy.deploy_env({**REQUIRED, "TRIAGE_TIMEOUT_S": "90"})["TRIAGE_TIMEOUT_S"] == "90"


def test_deploy_env_keeps_explicit_triage_key():
    env = deploy.deploy_env({**REQUIRED, "TRIAGE_API_KEY": "t", "CORS_ORIGINS": "o"})
    assert env["TRIAGE_API_KEY"] == "t"
    assert env["CORS_ORIGINS"] == "o"


def test_deploy_env_keeps_only_allowlisted_names():
    env = deploy.deploy_env({**REQUIRED, **FORBIDDEN, "UNRELATED": "x"})
    assert "AKASHML_API_KEY" not in env
    assert "UNRELATED" not in env
    assert not set(FORBIDDEN) & set(env)


@pytest.mark.parametrize("name", [n for n in REQUIRED if n != "AKASHML_API_KEY"] + ["AKASHML_API_KEY"])
def test_deploy_env_raises_when_required_missing(name):
    with pytest.raises(ValueError, match="TRIAGE_API_KEY" if name == "AKASHML_API_KEY" else name):
        deploy.deploy_env({**REQUIRED, name: ""})


@pytest.mark.parametrize("sdl", ["bootstrap", "image"])
def test_rendered_sdl_never_carries_console_or_senso_key(sdl):
    template = deploy.SDLS[sdl].read_text()
    out = deploy.render_sdl(template, deploy.deploy_env({**REQUIRED, **FORBIDDEN}))
    for name, value in FORBIDDEN.items():
        assert name not in out
        assert value not in out


def test_optional_vars_dropped_when_empty():
    out = deploy.render_sdl(deploy.SDLS["bootstrap"].read_text(), deploy.deploy_env({**REQUIRED, "GITHUB_TOKEN": ""}))
    for name in ("GITHUB_TOKEN", "GUILD_TRIGGER_KEY_ID", "GUILD_TRIGGER_SECRET", "CLICKHOUSE_DATABASE"):
        assert name not in out


def test_sent_env_names_lists_names_only():
    out = deploy.render_sdl(deploy.SDLS["bootstrap"].read_text(), deploy.deploy_env(REQUIRED))
    names = deploy.sent_env_names(out)
    assert "CLICKHOUSE_PASSWORD" in names
    assert "TRIAGE_API_KEY" in names
    assert all("=" not in n for n in names)


def test_error_message_hides_body_and_truncates():
    body = b'{"message": "' + b"m" * 500 + b'", "echo": "console-secret-value"}'
    msg = deploy.error_message(400, body)
    assert msg.startswith("400: ")
    assert "console-secret-value" not in msg
    assert len(msg) <= 305


def test_error_message_reads_error_field_and_survives_non_json():
    assert deploy.error_message(403, b'{"error": "Forbidden", "sdl": "secret"}') == "403: Forbidden"
    assert deploy.error_message(502, b"<html>secret</html>") == "502: "


def test_request_sends_custom_user_agent():
    request = deploy.build_request("POST", "/v1/deployments", "key", {"data": {"sdl": "x"}})
    agent = request.get_header("User-agent")
    assert agent and not agent.startswith("Python-urllib")
    assert request.get_header("X-api-key") == "key"


def test_error_message_shows_cloudflare_error_code():
    assert deploy.error_message(403, b"error code: 1010") == "403: error code: 1010"


def test_error_message_appends_akash_error_code():
    body = b'{"error": "Forbidden", "message": "", "code": "sealed_for_other_user", "sdl": "secret"}'
    assert deploy.error_message(403, body) == "403: Forbidden (code sealed_for_other_user)"


def test_bootstrap_sdl_renders_from_full_env():
    out = deploy.render_sdl(deploy.SDLS["bootstrap"].read_text(), deploy.deploy_env(REQUIRED))
    assert "python:3.12-slim-bookworm" in out
    assert "api.rootlane.xyz" in out


def test_cheapest_bid_picks_lowest_open_price():
    bids = [
        {"bid": {"id": {"provider": "p1"}, "state": "open", "price": {"amount": "5.0"}}},
        {"bid": {"id": {"provider": "p2"}, "state": "open", "price": {"amount": "1.5"}}},
        {"bid": {"id": {"provider": "p3"}, "state": "closed", "price": {"amount": "0.1"}}},
    ]
    assert deploy.cheapest_bid(bids)["id"]["provider"] == "p2"
