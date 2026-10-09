import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rootlane_toolbox.api import deps
from rootlane_toolbox.core.config import Settings
from rootlane_toolbox.api.dashboard import dashboard_router
from rootlane_toolbox.api.ingest import ingest_router
from rootlane_toolbox.storage.store import IncidentStore


class RowsResult:
    def __init__(self, rows):
        self.result_rows = rows


class FakeDB:
    """Serves canned rows keyed by a substring of the SQL and records inserts."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.inserted = {}
        self.columns = {}

    def query(self, sql, parameters=None):
        for needle, rows in self.responses.items():
            if needle in sql:
                return RowsResult(rows)
        return RowsResult([])

    def insert(self, table, data, column_names):
        self.inserted.setdefault(table, []).extend(data)
        self.columns[table] = column_names


@pytest.fixture
def make_app():
    def _make(settings=None, db=None, store=None, ro_db=None):
        deps.state.settings = settings or Settings(admin_token="secret", toolbox_api_key="agentkey")
        deps.state.db = db or FakeDB()
        deps.state.ro_db = ro_db or FakeDB()
        deps.state.store = store or IncidentStore(deps.state.db)
        app = FastAPI()
        app.include_router(dashboard_router)
        app.include_router(ingest_router)
        return TestClient(app)

    return _make
