from importlib.metadata import version as _get_version

from .fixtures import PG, pg, pg_11, pg_12, pg_13, pg_14, pg_15, pg_16, pg_17, pg_18, run_pg

__all__: tuple[str, ...] = (
    "PG",
    "run_pg",
    "pg",
    "pg_11",
    "pg_12",
    "pg_13",
    "pg_14",
    "pg_15",
    "pg_16",
    "pg_17",
    "pg_18",
)

__version__ = _get_version("pytest_pg")
