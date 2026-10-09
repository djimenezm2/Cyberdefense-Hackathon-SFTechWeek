import json
from pathlib import Path

import pytest

from rootlane_toolbox import models

FIX = Path(__file__).resolve().parents[2] / "ui" / "fixtures"


def _load(name):
    return json.loads((FIX / name).read_text())


@pytest.mark.parametrize(
    "name,model,many",
    [
        ("overview.json", models.Overview, False),
        ("events.json", models.Event, True),
        ("windows.json", models.Window, True),
        ("incidents.json", models.IncidentSummary, True),
        ("incident-detail.json", models.IncidentDetail, False),
        ("actions.json", models.Action, True),
    ],
)
def test_fixture_validates_and_round_trips(name, model, many):
    data = _load(name)
    items = data if many else [data]
    for item in items:
        obj = model.model_validate(item)
        dumped = obj.model_dump(mode="json")
        for key, value in item.items():
            assert dumped[key] == value, (name, key)
