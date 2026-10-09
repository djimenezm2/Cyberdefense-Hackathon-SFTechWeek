from ..core.broker import Broker, broker as default_broker
from ..core.config import Settings
from ..storage.store import IncidentStore


class AppState:
    """Process-wide holder for the objects built at startup."""

    settings: Settings
    db = None
    ro_db = None
    store: IncidentStore
    broker: Broker = default_broker
    sse_ping_s: float = 15.0


state = AppState()


def get_settings() -> Settings:
    return state.settings


def get_db():
    return state.db


def get_ro_db():
    return state.ro_db


def get_store() -> IncidentStore:
    return state.store


def get_broker() -> Broker:
    return state.broker


def get_ping_interval() -> float:
    return state.sse_ping_s
