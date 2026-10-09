import clickhouse_connect
from clickhouse_connect.driver import Client

from .config import Settings

READ_ONLY_QUERY_SETTINGS = {"max_result_rows": 200, "max_execution_time": 5}


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
    )
