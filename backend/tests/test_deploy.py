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


def test_deploy_env_maps_triage_key_and_defaults():
    env = deploy.deploy_env({"AKASHML_API_KEY": "k", "CLICKHOUSE_HOST": "h"})
    assert env["TRIAGE_API_KEY"] == "k"
    assert env["TRIAGE_BASE_URL"] == "https://api.akashml.com/v1"
    assert env["TRIAGE_MODEL"] == "zai-org/GLM-5.3"
    assert env["CORS_ORIGINS"] == "https://app.rootlane.xyz"
    assert env["ANALYZE_INTERVAL_S"] == "10"
    assert env["CLICKHOUSE_HOST"] == "h"


def test_deploy_env_keeps_explicit_triage_key():
    env = deploy.deploy_env({"AKASHML_API_KEY": "k", "TRIAGE_API_KEY": "t", "CORS_ORIGINS": "o"})
    assert env["TRIAGE_API_KEY"] == "t"
    assert env["CORS_ORIGINS"] == "o"


def test_bootstrap_sdl_renders_from_full_env():
    template = (_PATH.parent / "akash.bootstrap.sdl.yaml").read_text()
    names = [line.split("- ")[1].split("=")[0] for line in template.splitlines() if "=__SET_AT_DEPLOY__" in line]
    out = deploy.render_sdl(template, {name: "v" for name in names})
    assert "python:3.12-slim-bookworm" in out
    assert "api.rootlane.xyz" in out


def test_cheapest_bid_picks_lowest_open_price():
    bids = [
        {"bid": {"id": {"provider": "p1"}, "state": "open", "price": {"amount": "5.0"}}},
        {"bid": {"id": {"provider": "p2"}, "state": "open", "price": {"amount": "1.5"}}},
        {"bid": {"id": {"provider": "p3"}, "state": "closed", "price": {"amount": "0.1"}}},
    ]
    assert deploy.cheapest_bid(bids)["id"]["provider"] == "p2"
