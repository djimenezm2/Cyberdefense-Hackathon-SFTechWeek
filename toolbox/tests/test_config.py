from rootlane_toolbox.config import Settings


def test_from_env_reads_values_and_defaults():
    env = {
        "CLICKHOUSE_HOST": "svc.clickhouse.cloud",
        "CLICKHOUSE_USER": "default",
        "CLICKHOUSE_PASSWORD": "pw",
        "CLICKHOUSE_RO_USER": "agent_ro",
        "CLICKHOUSE_RO_PASSWORD": "ropw",
        "TOOLBOX_API_KEY": "k",
        "ADMIN_TOKEN": "t",
    }
    s = Settings.from_env(env)
    assert s.clickhouse_host == "svc.clickhouse.cloud"
    assert s.clickhouse_database == "rootlane"
    assert s.clickhouse_ro_user == "agent_ro"
    assert s.triage_base_url == "https://api.akashml.com/v1"
    assert s.triage_model == "zai-org/GLM-5.3"
    assert s.analyze_interval_s == 10
    assert s.sandbox_port == 3001
    assert not hasattr(s, "target_port")
    assert not hasattr(s, "akashml_api_key")


def test_cors_origins_default_and_list():
    assert Settings().cors_origin_list == ["https://app.rootlane.xyz"]
    s = Settings.from_env({"CORS_ORIGINS": "https://a.example, https://b.example"})
    assert s.cors_origin_list == ["https://a.example", "https://b.example"]
