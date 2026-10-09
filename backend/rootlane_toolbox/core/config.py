from collections.abc import Mapping

from pydantic import BaseModel


class Settings(BaseModel):
    """Runtime configuration, loaded from environment variables."""

    clickhouse_host: str = ""
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "rootlane"
    clickhouse_ro_user: str = "agent_ro"
    clickhouse_ro_password: str = ""
    toolbox_api_key: str = ""
    admin_token: str = ""
    ingest_token: str = ""
    triage_base_url: str = "https://api.akashml.com/v1"
    triage_model: str = "zai-org/GLM-5.3"
    triage_api_key: str = ""
    triage_timeout_s: int = 60
    analyze_interval_s: int = 10
    cors_origins: str = "https://app.rootlane.xyz"
    guild_workspace: str = ""
    guild_trigger_key_id: str = ""
    guild_trigger_secret: str = ""
    github_token: str = ""
    juice_shop_repo: str = ""
    public_domain: str = "rootlane.xyz"
    production_source_root: str = "/app/juice-shop"
    sandbox_port: int = 3001
    sandbox_build_timeout_s: int = 300
    sandbox_start_timeout_s: int = 120
    sandbox_request_timeout_s: float = 15.0

    @property
    def cors_origin_list(self) -> list[str]:
        """The comma-separated CORS origins as a list, blanks dropped."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        """Build Settings from an env mapping, keeping model defaults for absent keys."""
        values = {name: env[name.upper()] for name in cls.model_fields if name.upper() in env}
        return cls(**values)
