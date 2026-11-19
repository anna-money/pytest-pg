import contextlib
import dataclasses
import hashlib
import time
import uuid
from collections.abc import Callable, Generator
from http import HTTPStatus
from typing import Any

import docker
import docker.constants
import docker.errors
import pytest
import requests

from .utils import is_pg_ready, published_port, resolve_docker_host, resolve_image

LOCALHOST = "127.0.0.1"
READY_TIMEOUT = 30.0
POLL_INTERVAL = 0.05
DEFAULT_PG_USER = "postgres"
DEFAULT_PG_PASSWORD = "mysecretpassword"
DEFAULT_PG_DATABASE = "postgres"

POSTGRESQL_DATA_PATH = "/var/lib/postgresql/data"
PG_COMMAND = "-c fsync=off -c full_page_writes=off -c synchronous_commit=off -c bgwriter_lru_maxpages=0 -c jit=off"
PG_DEFAULT_MAX_CONNECTIONS = 100
DOCKER_DEFAULT_SHM_SIZE_MB = 64
XDIST_RUN_LABEL = "pytest-pg.xdist-run"
XDIST_CLEANUP_DOCKER_TIMEOUT = 5
PG_ISREADY_EXIT_CODES = {0, 1, 2, 3}
XDIST_SHARED_RUN_ID = "pytest_pg_shared_run_id"


@dataclasses.dataclass(frozen=True)
class PG:
    host: str
    port: int
    user: str
    password: str
    database: str


def _docker_client(timeout: int = docker.constants.DEFAULT_TIMEOUT_SECONDS) -> docker.APIClient:
    return docker.APIClient(base_url=resolve_docker_host(), version="auto", timeout=timeout)


def _ensure_image(docker_client: docker.APIClient, image: str) -> None:
    try:
        docker_client.inspect_image(image)
    except docker.errors.ImageNotFound:
        docker_client.pull(image)


def _create_container(
    docker_client: docker.APIClient,
    image: str,
    name: str,
    command: str,
    labels: dict[str, str] | None = None,
    shm_size: str | None = None,
) -> str:
    return docker_client.create_container(
        image=image,
        name=name,
        ports=[5432],
        detach=True,
        labels=labels,
        host_config=docker_client.create_host_config(
            # No port of our own choosing: Docker picks one and binds it in the same breath. Choosing
            # it here would mean naming a port that is free *now* and asking Docker to take it a
            # moment later — and under `pytest -n auto` the moment is long enough for another worker
            # to be handed the same number, which fails the start with "address already in use".
            port_bindings={5432: (LOCALHOST, None)},
            tmpfs=[POSTGRESQL_DATA_PATH],
            shm_size=shm_size,
        ),
        environment={
            "POSTGRES_HOST_AUTH_METHOD": "trust",
            "PGDATA": POSTGRESQL_DATA_PATH,
            "POSTGRES_INITDB_ARGS": "--no-sync",
        },
        command=command,
    )["Id"]


def _wait_until_ready(
    docker_client: docker.APIClient, container: str, image: str, ready_timeout: float, is_ready: Callable[[], bool]
) -> None:
    started_at = time.monotonic()
    while time.monotonic() - started_at < ready_timeout:
        if is_ready():
            return
        time.sleep(POLL_INTERVAL)
    container_logs = docker_client.logs(container).decode()
    pytest.fail(f"Failed to start postgres using {image} in {ready_timeout} seconds: {container_logs}")


def _is_host_pg_ready(port: int) -> bool:
    return is_pg_ready(
        host=LOCALHOST,
        port=port,
        database=DEFAULT_PG_DATABASE,
        user=DEFAULT_PG_USER,
        password=DEFAULT_PG_PASSWORD,
    )


def _pg_at(port: int, database: str = DEFAULT_PG_DATABASE) -> PG:
    return PG(host=LOCALHOST, port=port, user=DEFAULT_PG_USER, password=DEFAULT_PG_PASSWORD, database=database)


def _exec(docker_client: docker.APIClient, container: str, command: list[str]) -> tuple[int, str]:
    exec_id = docker_client.exec_create(container, command, user=DEFAULT_PG_USER)["Id"]
    output = docker_client.exec_start(exec_id).decode()
    return docker_client.exec_inspect(exec_id)["ExitCode"], output


def _exec_or_fail(docker_client: docker.APIClient, container: str, command: list[str]) -> None:
    exit_code, output = _exec(docker_client, container, command)
    if exit_code != 0:
        pytest.fail(f"`{' '.join(command)}` failed in {container} with exit code {exit_code}: {output}")


@contextlib.contextmanager
def run_pg(image: str, ready_timeout: float = READY_TIMEOUT) -> Generator[PG, None, None]:
    docker_client = _docker_client()
    _ensure_image(docker_client, image)

    container_id = _create_container(docker_client, image, f"pytest-pg-{uuid.uuid4()}", PG_COMMAND)

    try:
        docker_client.start(container=container_id)
        port = published_port(docker_client, container_id)

        _wait_until_ready(docker_client, container_id, image, ready_timeout, lambda: _is_host_pg_ready(port))

        yield _pg_at(port)
    finally:
        # Force, and one call: a container that never started cannot be killed, and a teardown that
        # raises on that hides whatever went wrong with the start.
        docker_client.remove_container(container_id, v=True, force=True)


def _xdist_container_name(run_id: str, image: str) -> str:
    image_hash = hashlib.blake2b(image.encode(), digest_size=4).hexdigest()
    return f"pytest-pg-{run_id}-{image_hash}"


def _create_container_if_absent(
    docker_client: docker.APIClient, image: str, name: str, run_id: str, worker_count: int
) -> None:
    command_with_capacity_of_a_container_per_worker = (
        f"{PG_COMMAND} -c max_connections={PG_DEFAULT_MAX_CONNECTIONS * worker_count}"
    )
    try:
        _create_container(
            docker_client,
            image,
            name,
            command_with_capacity_of_a_container_per_worker,
            labels={XDIST_RUN_LABEL: run_id},
            shm_size=f"{DOCKER_DEFAULT_SHM_SIZE_MB * worker_count}m",
        )
    except docker.errors.APIError as error:
        another_worker_took_the_name = error.status_code == HTTPStatus.CONFLICT
        if not another_worker_took_the_name:
            raise


def _start_once_created(docker_client: docker.APIClient, name: str, timeout: float) -> None:
    started_at = time.monotonic()
    while True:
        try:
            docker_client.start(container=name)
            return
        except docker.errors.NotFound:
            if time.monotonic() - started_at > timeout:
                raise
            time.sleep(POLL_INTERVAL)


def _is_shared_pg_ready(docker_client: docker.APIClient, container: str, port: int) -> bool:
    try:
        exit_code, output = _exec(docker_client, container, ["pg_isready", "-q", "-h", "localhost"])
    except docker.errors.APIError as error:
        container_not_running_yet = error.status_code == HTTPStatus.CONFLICT
        if container_not_running_yet:
            return False
        raise
    if exit_code not in PG_ISREADY_EXIT_CODES:
        pytest.fail(f"`pg_isready` cannot run as {DEFAULT_PG_USER} in {container} (exit code {exit_code}): {output}")
    is_final_server_accepting_tcp = exit_code == 0
    return is_final_server_accepting_tcp and _is_host_pg_ready(port)


def _recreate_database(docker_client: docker.APIClient, container: str, database: str) -> None:
    _exec_or_fail(
        docker_client,
        container,
        [
            "psql",
            "--quiet",
            "--set=ON_ERROR_STOP=1",
            f'--command=DROP DATABASE IF EXISTS "{database}" WITH (FORCE)',
            f'--command=CREATE DATABASE "{database}"',
        ],
    )


@contextlib.contextmanager
def _run_xdist_worker_pg(image: str, run_id: str, worker_id: str, worker_count: int) -> Generator[PG, None, None]:
    docker_client = _docker_client()
    _ensure_image(docker_client, image)

    name = _xdist_container_name(run_id, image)
    _create_container_if_absent(docker_client, image, name, run_id, worker_count)
    _start_once_created(docker_client, name, READY_TIMEOUT)
    port = published_port(docker_client, name)

    _wait_until_ready(docker_client, name, image, READY_TIMEOUT, lambda: _is_shared_pg_ready(docker_client, name, port))

    database = f"pytest_{worker_id}"
    _recreate_database(docker_client, name, database)

    yield _pg_at(port, database)


def remove_xdist_containers(run_id: str) -> None:
    try:
        docker_client = _docker_client(timeout=XDIST_CLEANUP_DOCKER_TIMEOUT)
        containers = docker_client.containers(all=True, filters={"label": f"{XDIST_RUN_LABEL}={run_id}"})
    except (docker.errors.DockerException, requests.exceptions.RequestException):
        return
    for container in containers:
        with contextlib.suppress(docker.errors.APIError, requests.exceptions.RequestException):
            docker_client.remove_container(container["Id"], v=True, force=True)


def _run_session_pg(pytestconfig: pytest.Config, version: str) -> contextlib.AbstractContextManager[PG]:
    image = resolve_image(str(pytestconfig.getini("pg_docker_image_name")), version)
    workerinput: dict[str, Any] = getattr(pytestconfig, "workerinput", {})
    shared_run_id = workerinput.get(XDIST_SHARED_RUN_ID)
    if shared_run_id:
        return _run_xdist_worker_pg(image, shared_run_id, workerinput["workerid"], workerinput["workercount"])
    return run_pg(image)


@pytest.fixture(scope="session")
def pg(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _run_session_pg(pytestconfig, "latest") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_14(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _run_session_pg(pytestconfig, "14") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_15(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _run_session_pg(pytestconfig, "15") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_16(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _run_session_pg(pytestconfig, "16") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_17(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _run_session_pg(pytestconfig, "17") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_18(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _run_session_pg(pytestconfig, "18") as pg:
        yield pg
