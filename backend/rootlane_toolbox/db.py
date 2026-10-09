import threading
from collections.abc import Callable

import clickhouse_connect
from clickhouse_connect.driver import Client

from .config import Settings


def clickhouse_client(settings: Settings, *, read_only: bool = False) -> Client:
    """
    Build a secure ClickHouse Cloud client (HTTPS on 8443).

    Args:
        settings (Settings): Connection settings.
        read_only (bool): Use the read-only user instead of the admin user.

    Returns:
        Client: A connected clickhouse-connect client.
    """
    user = settings.clickhouse_ro_user if read_only else settings.clickhouse_user
    password = settings.clickhouse_ro_password if read_only else settings.clickhouse_password
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=8443,
        secure=True,
        username=user,
        password=password,
        database=settings.clickhouse_database,
        autogenerate_session_id=False,
    )


class ReadOnlyUnavailable(Exception):
    """Raised when the read-only ClickHouse client cannot be built."""


class LazyClient:
    """Builds the wrapped client on first use and forwards every attribute to it."""

    def __init__(self, factory: Callable[[], Client]):
        self._factory = factory
        self._client: Client | None = None
        self._lock = threading.Lock()

    def _resolve(self) -> Client:
        with self._lock:
            if self._client is None:
                try:
                    self._client = self._factory()
                except Exception as error:
                    raise ReadOnlyUnavailable(
                        "read-only ClickHouse user is unavailable"
                    ) from error
            return self._client

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)


def lazy_read_only_client(settings: Settings) -> LazyClient:
    """A read-only client that connects on first use, so startup does not depend on the user."""
    return LazyClient(lambda: clickhouse_client(settings, read_only=True))
