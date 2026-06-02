from importlib.metadata import version as _get_version

import pytest

from .fixtures import PG, pg, pg_14, pg_15, pg_16, pg_17, pg_18, run_pg

__all__: tuple[str, ...] = (
    "PG",
    "run_pg",
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
