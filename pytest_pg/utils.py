import asyncio
import socket
from typing import Any, Optional, Protocol


class IsReadyFunc(Protocol):
    def __call__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
    ) -> bool:
        ...


def _try_get_is_postgres_ready_based_on_psycopg2() -> Optional[IsReadyFunc]:
    try:
        # noinspection PyPackageRequirements
        import psycopg2

        def _is_postgres_ready(**params: Any) -> bool:
            try:
                with psycopg2.connect(**params):
                    return True
            except psycopg2.OperationalError:
                return False

        return _is_postgres_ready
    except ImportError:
        return None


def _try_get_is_postgres_ready_based_on_asyncpg() -> Optional[IsReadyFunc]:
    try:
        # noinspection PyPackageRequirements
        import asyncpg

        def _is_postgres_ready(**params: Any) -> bool:
            async def _is_postgres_ready_async() -> bool:
                try:
                    connection = await asyncpg.connect(**params)
                    await connection.close()
                    return True
                except (asyncpg.exceptions.PostgresError, OSError):
                    return False

            return asyncio.run(_is_postgres_ready_async())

        return _is_postgres_ready

    except ImportError:
        return None


def _get_dummy_is_postgresql_ready() -> IsReadyFunc:
    def _is_postgres_ready(**_: Any) -> bool:
        return True

    return _is_postgres_ready


is_pg_ready = (
    _try_get_is_postgres_ready_based_on_asyncpg()
    or _try_get_is_postgres_ready_based_on_psycopg2()
    or _get_dummy_is_postgresql_ready()
)


def find_unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]  # type: ignore
