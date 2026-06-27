# pyright: reportPrivateUsage=false
import contextlib
import datetime
import json
import pathlib
from collections.abc import Generator
from typing import Any

import docker
import docker.errors
import pytest

import pytest_pg
from pytest_pg.fixtures import (
    PG_COMMAND,
    PG_ENVIRONMENT,
    _create_pg_container,
    _docker_exec,
    _ensure_running_reuse_container,
    _reap_stale_reuse_databases,
    _reuse_container_name,
)
from pytest_pg.utils import find_unused_local_port, resolve_docker_host

IMAGE = "postgres:16"
REUSE_CONTAINER_NAME = _reuse_container_name(IMAGE, PG_COMMAND, PG_ENVIRONMENT)
DOCKER_ENDPOINT = resolve_docker_host()


@pytest.fixture
def docker_client() -> Generator[Any, None, None]:
    client = docker.APIClient(base_url=DOCKER_ENDPOINT, version="auto")
    try:
        yield client
    finally:
        with contextlib.suppress(docker.errors.APIError):
            client.remove_container(REUSE_CONTAINER_NAME, v=True, force=True)


def _database_names(client: Any, container: str) -> set[str]:
    listing = _docker_exec(client, container, ["psql", "-U", "postgres", "-tAc", "SELECT datname FROM pg_database"])
    return set(listing.split())


def test_reusable_pg_persists_container_and_drops_database(docker_client: Any) -> None:
    with pytest_pg.run_reusable_pg(IMAGE) as pg:
        assert pg.database.startswith("pytest_master_")
        assert pg.database in _database_names(docker_client, REUSE_CONTAINER_NAME)
        database = pg.database

    assert docker_client.inspect_container(REUSE_CONTAINER_NAME)["State"]["Running"] is True
    assert database not in _database_names(docker_client, REUSE_CONTAINER_NAME)


def test_reusable_pg_reuses_the_same_container(docker_client: Any) -> None:
    with pytest_pg.run_reusable_pg(IMAGE) as first:
        first_id = docker_client.inspect_container(REUSE_CONTAINER_NAME)["Id"]
    with pytest_pg.run_reusable_pg(IMAGE) as second:
        second_id = docker_client.inspect_container(REUSE_CONTAINER_NAME)["Id"]

    assert first_id == second_id
    assert first.port == second.port
    assert first.database != second.database


def test_reap_drops_only_stale_pytest_databases(docker_client: Any) -> None:
    _ensure_running_reuse_container(docker_client, IMAGE, REUSE_CONTAINER_NAME, 30.0)
    now = datetime.datetime.now(datetime.timezone.utc)
    stale = f"pytest_gw0_{(now - datetime.timedelta(days=3)).strftime('%Y%m%d%H%M%S')}_deadbeef"
    fresh = f"pytest_gw0_{now.strftime('%Y%m%d%H%M%S')}_beefcafe"
    for database in (stale, fresh, "keep_me"):
        _docker_exec(docker_client, REUSE_CONTAINER_NAME, ["createdb", "-U", "postgres", database])

    _reap_stale_reuse_databases(docker_client, REUSE_CONTAINER_NAME, datetime.timedelta(days=2))

    databases = _database_names(docker_client, REUSE_CONTAINER_NAME)
    assert stale not in databases
    assert fresh in databases
    assert "keep_me" in databases


def test_ensure_running_recreates_a_stopped_container(docker_client: Any) -> None:
    _create_pg_container(docker_client, IMAGE, REUSE_CONTAINER_NAME, find_unused_local_port())
    docker_client.kill(REUSE_CONTAINER_NAME)
    stopped_id = docker_client.inspect_container(REUSE_CONTAINER_NAME)["Id"]

    _ensure_running_reuse_container(docker_client, IMAGE, REUSE_CONTAINER_NAME, 30.0)

    info = docker_client.inspect_container(REUSE_CONTAINER_NAME)
    assert info["State"]["Running"] is True
    assert info["Id"] != stopped_id


_INNER_TEST = """
import json
import os
import pathlib

import pytest


@pytest.mark.parametrize("n", range(4))
def test_record(pg_16, n):
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    record = pathlib.Path(os.environ["PYTEST_PG_RECORD_DIR"]) / f"{worker}.json"
    record.write_text(json.dumps({"port": pg_16.port, "database": pg_16.database}))
    assert pg_16.database.startswith("pytest_")
"""


def test_xdist_workers_share_one_container_with_distinct_databases(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, docker_client: Any
) -> None:
    records = tmp_path / "records"
    records.mkdir()
    monkeypatch.setenv("PYTEST_PG_RECORD_DIR", str(records))
    if DOCKER_ENDPOINT is not None:
        monkeypatch.setenv("DOCKER_HOST", DOCKER_ENDPOINT)
    pytester.makeconftest('pytest_plugins = ["pytest_pg"]')
    pytester.makepyfile(_INNER_TEST)

    result = pytester.runpytest_subprocess("-o", "pg_mode=reusable", "-n", "2")
    result.assert_outcomes(passed=4)

    recorded = [json.loads(path.read_text()) for path in records.glob("*.json")]
    assert len(recorded) == 2
    assert len({record["port"] for record in recorded}) == 1
    assert len({record["database"] for record in recorded}) == 2
