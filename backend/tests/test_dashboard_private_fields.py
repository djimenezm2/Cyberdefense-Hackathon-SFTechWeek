import json

import pytest

from rootlane_toolbox.core.models import IncidentDetail
from rootlane_toolbox.storage.store import IncidentStore, now_iso
from tests.conftest import FakeDB

SECRET = "Bearer eyJhbGciOiJub25lIn0.secret-token-value."
ADMIN = {"X-Admin-Token": "secret"}


def _db():
    detail = IncidentDetail.model_validate(dict(
        id="inc_01", title="t", status="pending_approval", severity="high", category="identity",
        opened_at=now_iso(), summary="s",
        proposal={"proposal_hash": "p_abc", "diff": "d", "rule_yaml": "r", "report": "x"},
        reproduction={"method": "GET", "path": "/rest/basket/2", "headers": {"Authorization": SECRET},
                      "body": None, "expected_blocked_status": 401},
        last_verify={"hash": "p_abc", "passed": True},
    ))
    return FakeDB(responses={"SELECT document FROM incidents": [[detail.model_dump_json()]]})


def _assert_private_fields_absent(response):
    assert response.status_code == 200
    body = response.json()
    assert "reproduction" not in body and "last_verify" not in body
    assert "secret-token-value" not in response.text


def test_detail_never_returns_the_reproduction_or_verify_internals(make_app):
    client = make_app(db=_db())
    _assert_private_fields_absent(client.get("/api/incidents/inc_01"))


@pytest.mark.parametrize("action,body", [
    ("approve", {"approver": "David"}),
    ("reject", {"approver": "David", "reason": "no"}),
])
def test_decisions_never_return_them_but_keep_them_stored(make_app, action, body):
    db = _db()
    client = make_app(db=db, store=IncidentStore(db))
    _assert_private_fields_absent(client.post(f"/api/incidents/inc_01/{action}", json=body, headers=ADMIN))
    saved = json.loads(db.inserted["incidents"][0][-1])
    assert saved["reproduction"]["headers"]["Authorization"] == SECRET
    assert saved["last_verify"] == {"hash": "p_abc", "passed": True}
