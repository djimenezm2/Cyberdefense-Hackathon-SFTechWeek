import httpx

from .config import Settings


class GuildTrigger:
    """Starts a Guild agent session via the API trigger; degrades gracefully."""

    def __init__(self, settings: Settings, *, http: httpx.Client | None = None):
        self._settings = settings
        self._http = http or httpx.Client(base_url="https://api.guild.ai", timeout=20)

    def start_session(self, incident: dict) -> str | None:
        """
        Start a Guild session for an incident.

        Args:
            incident (dict): The incident; its `id` is passed as agent input.

        Returns:
            str | None: The session id, or None when no trigger is configured or the call fails.
        """
        s = self._settings
        if not (s.guild_workspace and s.guild_trigger_key_id and s.guild_trigger_secret):
            return None
        owner, _, workspace = s.guild_workspace.partition("/")
        try:
            resp = self._http.post(
                f"/v1/workspaces/{owner}/{workspace or owner}/sessions",
                auth=(s.guild_trigger_key_id, s.guild_trigger_secret),
                json={"session_type": "api_trigger", "agent_input": {"incident_id": incident["id"]}},
            )
            resp.raise_for_status()
            return resp.json()["id"]
        except (httpx.HTTPError, KeyError, ValueError):
            return None
