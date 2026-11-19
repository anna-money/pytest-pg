from importlib.metadata import version as _get_version
from typing import Any

import pytest

from .fixtures import (
    PG,
    is_xdist_sharing_enabled,
    pg,
    pg_14,
    pg_15,
    pg_16,
    pg_17,
    pg_18,
    remove_xdist_containers,
    run_pg,
)

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

_XDIST_TESTRUN_UIDS = pytest.StashKey[set[str]]()


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
    if is_xdist_sharing_enabled(node.config):
        node.config.stash.setdefault(_XDIST_TESTRUN_UIDS, set()).add(node.workerinput["testrunuid"])


def pytest_unconfigure(config: pytest.Config) -> None:
    testrun_uids = config.stash.get(_XDIST_TESTRUN_UIDS, None)
    if testrun_uids:
        remove_xdist_containers(testrun_uids)
