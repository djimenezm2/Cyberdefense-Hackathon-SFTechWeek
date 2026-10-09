import pytest

from rootlane_toolbox import __main__ as cli
from rootlane_toolbox.storage.store import IncidentStore
from tests.conftest import FakeDB
from tests.test_tools_reproduce_verify import Broker, IncidentDB

ARGS = ["open-incident", "--title", "Forged token served", "--severity", "high",
        "--category", "identity", "--summary", "Requests served without login"]


@pytest.fixture
def store(monkeypatch):
    built = IncidentStore(IncidentDB(), broker=Broker())
    monkeypatch.setattr(cli, "_build_store", lambda settings: built)
    return built


def test_open_incident_prints_only_the_id_and_stores_the_incident(store, capsys):
    assert cli.main(ARGS) == 0
    incident_id = capsys.readouterr().out.strip()
    assert incident_id.startswith("inc_") and " " not in incident_id
    detail = store.get(incident_id)
    assert (detail.title, detail.status, detail.severity, detail.category) == (
        "Forged token served", "investigating", "high", "identity")
    assert detail.summary == "Requests served without login"


def test_open_incident_publishes_the_new_incident(store):
    cli.main(ARGS)
    assert [event for event, _ in store._broker.events] == ["incident_update"]


@pytest.mark.parametrize("flag,value", [("--severity", "urgent"), ("--category", "Bad Category")])
def test_bad_enum_values_exit_non_zero_and_store_nothing(store, flag, value):
    args = list(ARGS)
    args[args.index(flag) + 1] = value
    with pytest.raises(SystemExit) as exit_info:
        cli.main(args)
    assert exit_info.value.code != 0
    assert store._client.inserted == {}


def test_missing_title_exits_non_zero(store):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["open-incident", "--severity", "high", "--category", "identity", "--summary", "s"])
    assert exit_info.value.code != 0
