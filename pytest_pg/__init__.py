from importlib.metadata import version as _get_version

import pytest

from .fixtures import PG, PgMode, pg, pg_14, pg_15, pg_16, pg_17, pg_18, run_pg, run_reusable_pg

__all__: tuple[str, ...] = (
    "PG",
    "PgMode",
    "run_pg",
    "run_reusable_pg",
    "pg",
    "pg_14",
    "pg_15",
    "pg_16",
    "pg_17",
    "pg_18",
)

__version__ = _get_version("pytest_pg")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        "pg_docker_image_name",
        help="Base PostgreSQL image (registry and name, without tag); the version tag is appended.",
        default="postgres",
    )
    parser.addini(
        "pg_mode",
        help='PostgreSQL container mode: "ephemeral" (default, a fresh container per session) or "reusable" (a long-living container reused across runs, with one fresh database per xdist worker).',
        default="ephemeral",
    )
    parser.addini(
        "pg_database_max_age_days",
        help="Reusable mode only: at session start, drop leftover pytest databases older than this many days (default 2).",
        default="2",
    )
