import json
import uuid
from typing import Any

import docker
import pytest

from pytest_pg.fixtures import xdist_containers
from pytest_pg.utils import resolve_docker_host

pytest.importorskip("xdist")

WORKERS = 3
TESTS_PER_WORKER = 3
HOST_DOCKER_HOST = resolve_docker_host()

INNER_TESTS_RECORDING_WHAT_EACH_WORKER_GOT = """
import json
import os

import docker

from pytest_pg.utils import resolve_docker_host


def _record(pg, pytestconfig):
    worker_id = pytestconfig.workerinput["workerid"]
    docker_client = docker.APIClient(base_url=resolve_docker_host(), version="auto")
    containers = [
        container["Id"]
        for container in docker_client.containers()
        if any(port.get("PublicPort") == pg.port for port in container["Ports"])
    ]
    exec_id = docker_client.exec_create(
        containers[0], ["psql", "-d", pg.database, "-tAc", "select current_database()"], user="postgres"
    )["Id"]
    current_database = docker_client.exec_start(exec_id).decode().strip()
    record = {"worker": worker_id, "port": pg.port, "database": pg.database, "current_database": current_database}
    with open(os.path.join(os.environ["PG_RECORDS"], f"{worker_id}.json"), "w") as f:
        json.dump(record, f)


def test_0(pg_18, pytestconfig):
    _record(pg_18, pytestconfig)


def test_1(pg_18, pytestconfig):
    _record(pg_18, pytestconfig)


def test_2(pg_18, pytestconfig):
    _record(pg_18, pytestconfig)
"""


def _run(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, *args: str) -> tuple[str, list[dict[str, str]]]:
    records = pytester.mkdir("records")
    monkeypatch.setenv("PG_RECORDS", str(records))
    if HOST_DOCKER_HOST:
        monkeypatch.setenv("DOCKER_HOST", HOST_DOCKER_HOST)
    pytester.makepyfile(test_inner=INNER_TESTS_RECORDING_WHAT_EACH_WORKER_GOT)
    testrun_uid = uuid.uuid4().hex
    every_worker_runs_every_test = ("--dist", "each")
    result = pytester.runpytest_subprocess(
        "-n", str(WORKERS), *every_worker_runs_every_test, f"--testrunuid={testrun_uid}", *args
    )
    result.assert_outcomes(passed=TESTS_PER_WORKER * WORKERS)
    return testrun_uid, [json.loads(path.read_text()) for path in sorted(records.iterdir())]


def _containers_of(testrun_uid: str) -> list[dict[str, Any]]:
    return xdist_containers(docker.APIClient(base_url=HOST_DOCKER_HOST, version="auto"), testrun_uid)


def test_workers_share_one_container_with_a_database_each(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    testrun_uid, records = _run(pytester, monkeypatch)

    assert len(records) == WORKERS
    assert len({record["port"] for record in records}) == 1
    assert sorted(record["database"] for record in records) == [f"pytest_gw{i}" for i in range(WORKERS)]
    assert all(record["current_database"] == record["database"] for record in records)
    assert _containers_of(testrun_uid) == []


def test_sharing_can_be_switched_off(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    testrun_uid, records = _run(pytester, monkeypatch, "-o", "pg_xdist_shared_container=false")

    assert len(records) == WORKERS
    assert len({record["port"] for record in records}) == WORKERS
    assert all(record["database"] == "postgres" for record in records)
    assert _containers_of(testrun_uid) == []


def test_xdist_run_without_pg_needs_no_docker(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent/docker.sock")
    pytester.makepyfile(test_inner="def test_without_pg():\n    pass\n")

    result = pytester.runpytest_subprocess("-n", "2")

    result.assert_outcomes(passed=1)
    assert result.ret == pytest.ExitCode.OK
