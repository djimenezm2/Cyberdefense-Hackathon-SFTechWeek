import json
from typing import Protocol

import httpx

from ..core.config import Settings

_PROMPT = (
    "You are a security analyst. Given behavioural features of recent web traffic, "
    "summarised per principal and per IP, judge whether anything looks like an attack "
    'or abuse. Reply with JSON {"verdict": one of ignore|watch|escalate, '
    '"rationale": one short sentence}. Escalate only on strong evidence. '
    "Do not assume any particular attack type."
)
_VERDICTS = ("ignore", "watch", "escalate")


class Decider(Protocol):
    """Turns window features into a verdict; implementations are interchangeable."""

    def decide(self, features: dict) -> dict: ...


class AkashMLDecider:
    """Decides a window's verdict and rationale with an AkashML open model."""

    def __init__(self, settings: Settings, *, http: httpx.Client | None = None):
        self._settings = settings
        self._http = http or httpx.Client(
            base_url=settings.triage_base_url,
            headers={"Authorization": f"Bearer {settings.triage_api_key}"},
            timeout=20,
        )

    def decide(self, features: dict) -> dict:
        """
        Ask the model for a verdict on the window.

        Args:
            features (dict): The output of `compute_features`.

        Returns:
            dict: `verdict` (ignore|watch|escalate), `rationale` and `model`. An
                unparseable or unknown verdict becomes `watch`.

        Raises:
            httpx.HTTPError: If the request fails.
        """
        resp = self._http.post(
            "/chat/completions",
            json={
                "model": self._settings.triage_model,
                "messages": [
                    {"role": "system", "content": _PROMPT},
                    {"role": "user", "content": json.dumps(features)},
                ],
                "temperature": 0,
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"] or ""
        parsed = _first_json(content)
        verdict = parsed.get("verdict", "watch")
        if verdict not in _VERDICTS:
            verdict = "watch"
        return {
            "verdict": verdict,
            "rationale": str(parsed.get("rationale", "")),
            "model": self._settings.triage_model,
        }


def _first_json(text: str) -> dict:
    """Parse the first JSON object in the model's reply, tolerating prose around it."""
    start = text.find("{")
    if start < 0:
        return {}
    try:
        parsed = json.loads(text[start : text.rfind("}") + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
