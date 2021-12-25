import asyncio
import logging
import socket

logger = logging.getLogger(__package__)


def _try_get_is_postgres_ready_based_on_psycopg2():
    try:
        # noinspection PyPackageRequirements
        import psycopg2

        def _is_postgres_ready(**params):
            try:
                with psycopg2.connect(**params):
                    return True
            except psycopg2.Error:
                logger.debug("Failed to connect to postgresql", exc_info=True)
                return False

        return _is_postgres_ready
    except ImportError:
        logger.debug("Failed to find psycopg2")
        return None


def _try_get_is_postgres_ready_based_on_asyncpg():
    try:
        # noinspection PyPackageRequirements
        import asyncpg

        def _is_postgres_ready(**params):
            async def _is_postgres_ready_async():
                try:
                    connection = await asyncpg.connect(**params)
                    await connection.close()
                    return True
                except (asyncpg.exceptions.PostgresError, OSError):
                    logger.debug("Failed to connect to postgresql", exc_info=True)
                    return False

            return asyncio.run(_is_postgres_ready_async())

        return _is_postgres_ready

    except ImportError:
        logger.debug("Failed to find asyncpg")
        return None


def _get_dummy_is_postgresql_ready():
    def _is_postgres_ready(**_):
        return True

    return _is_postgres_ready


is_pg_ready = (
    _try_get_is_postgres_ready_based_on_asyncpg()
    or _try_get_is_postgres_ready_based_on_psycopg2()
    or _get_dummy_is_postgresql_ready()
)


def find_unused_local_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
