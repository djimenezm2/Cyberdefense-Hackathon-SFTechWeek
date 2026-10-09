import json

import pytest

from rootlane_toolbox.core.models import IncidentDetail
from rootlane_toolbox.storage.store import IncidentStore, now_iso
from tests.conftest import FakeDB


def _db(with_proposal=True, status="pending_approval"):
    fields = dict(
        id="inc_01",
        title="t",
        status=status,
        severity="high",
        category="identity",
        opened_at=now_iso(),
        summary="s",
    )
    if with_proposal:
        fields["proposal"] = {
            "proposal_hash": "p_abc",
            "diff": "d",
            "rule_yaml": "r",
            "report": "x",
        }
    detail = IncidentDetail.model_validate(fields)
    return FakeDB(responses={"SELECT document FROM incidents": [[detail.model_dump_json()]]})


def test_approve_requires_admin_token(make_app):
    client = make_app(db=_db())
    r = client.post("/api/incidents/inc_01/approve", json={"approver": "David"})
    assert r.status_code == 401


def test_wrong_admin_token_is_rejected(make_app):
    client = make_app(db=_db())
    r = client.post(
        "/api/incidents/inc_01/approve",
        json={"approver": "David"},
        headers={"X-Admin-Token": "nope"},
    )
    assert r.status_code == 401


def test_approve_sets_status_and_approval_and_persists(make_app):
    db = _db()
    client = make_app(db=db, store=IncidentStore(db))
    r = client.post(
        "/api/incidents/inc_01/approve",
        json={"approver": "David"},
        headers={"X-Admin-Token": "secret"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "applying"
    assert body["approval"]["decision"] == "approve"
    assert body["approval"]["approver"] == "David"
    assert body["approval"]["proposal_hash"] == "p_abc"
    assert body["steps"][-1]["kind"] == "approval"
    saved = json.loads(db.inserted["incidents"][0][-1])
    assert saved["status"] == "applying"


def test_reject_sets_status_rejected(make_app):
    db = _db()
    client = make_app(db=db, store=IncidentStore(db))
    r = client.post(
        "/api/incidents/inc_01/reject",
        json={"approver": "David", "reason": "risky"},
        headers={"X-Admin-Token": "secret"},
    )
    assert r.json()["status"] == "rejected"
    assert r.json()["approval"]["reason"] == "risky"


def test_decision_without_proposal_is_409(make_app):
    client = make_app(db=_db(with_proposal=False))
    r = client.post(
        "/api/incidents/inc_01/approve",
        json={"approver": "David"},
        headers={"X-Admin-Token": "secret"},
    )
    assert r.status_code == 409


@pytest.mark.parametrize("status", ["applied", "rejected", "investigating"])
@pytest.mark.parametrize("action", ["approve", "reject"])
def test_decision_outside_pending_approval_is_409_and_persists_nothing(make_app, status, action):
    db = _db(status=status)
    client = make_app(db=db, store=IncidentStore(db))
    r = client.post(
        f"/api/incidents/inc_01/{action}",
        json={"approver": "David", "reason": "x"},
        headers={"X-Admin-Token": "secret"},
    )
    assert r.status_code == 409
    assert "incidents" not in db.inserted


def test_non_ascii_admin_token_is_401_not_500(make_app):
    client = make_app(db=_db())
    r = client.post(
        "/api/incidents/inc_01/approve",
        json={"approver": "David"},
        headers={"X-Admin-Token": "é".encode("latin-1")},
    )
    assert r.status_code == 401
