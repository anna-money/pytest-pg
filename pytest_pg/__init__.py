import uuid
from importlib.metadata import version as _get_version
from typing import Any

import pytest

from .fixtures import PG, XDIST_SHARED_RUN_ID, pg, pg_14, pg_15, pg_16, pg_17, pg_18, remove_xdist_containers, run_pg

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

_XDIST_SHARED_RUN_ID = pytest.StashKey[str]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        "pg_docker_image_name",
        help="Base PostgreSQL image (registry and name, without tag); the version tag is appended.",
        default="postgres",
    )
    parser.addini(
        "pg_xdist_shared_container",
        type="bool",
        help="Under pytest-xdist, run one container per run shared by all workers, each with its own database.",
        default=True,
    )


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node: Any) -> None:
    is_local_worker = bool(node.gateway.spec.popen)
    if is_local_worker and node.config.getini("pg_xdist_shared_container"):
        node.workerinput[XDIST_SHARED_RUN_ID] = node.config.stash.setdefault(_XDIST_SHARED_RUN_ID, uuid.uuid4().hex)


def pytest_unconfigure(config: pytest.Config) -> None:
    shared_run_id = config.stash.get(_XDIST_SHARED_RUN_ID, None)
    if shared_run_id:
        remove_xdist_containers(shared_run_id)
