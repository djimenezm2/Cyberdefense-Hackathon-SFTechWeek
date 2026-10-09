from .config import Settings
from .store import IncidentStore


class AppState:
    """Process-wide holder for the objects built at startup."""

    settings: Settings
    db = None
    ro_db = None
    store: IncidentStore


state = AppState()


def get_settings() -> Settings:
    return state.settings


def get_db():
    return state.db


def get_ro_db():
    return state.ro_db


def get_store() -> IncidentStore:
    return state.store
