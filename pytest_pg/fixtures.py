import contextlib
import dataclasses
import time
import uuid
from collections.abc import Generator

import docker
import docker.errors
import pytest

from .utils import is_pg_ready, published_port, resolve_docker_host, resolve_image

LOCALHOST = "127.0.0.1"
DEFAULT_PG_USER = "postgres"
DEFAULT_PG_PASSWORD = "mysecretpassword"
DEFAULT_PG_DATABASE = "postgres"


@dataclasses.dataclass(frozen=True)
class PG:
    host: str
    port: int
    user: str
    password: str
    database: str


@contextlib.contextmanager
def run_pg(image: str, ready_timeout: float = 30.0) -> Generator[PG, None, None]:
    docker_client = docker.APIClient(base_url=resolve_docker_host(), version="auto")
    try:
        docker_client.inspect_image(image)
    except docker.errors.ImageNotFound:
        docker_client.pull(image)

    postgresql_data_path = "/var/lib/postgresql/data"

    container = docker_client.create_container(
        image=image,
        name=f"pytest-pg-{uuid.uuid4()}",
        ports=[5432],
        detach=True,
        host_config=docker_client.create_host_config(
            # No port of our own choosing: Docker picks one and binds it in the same breath. Choosing
            # it here would mean naming a port that is free *now* and asking Docker to take it a
            # moment later — and under `pytest -n auto` the moment is long enough for another worker
            # to be handed the same number, which fails the start with "address already in use".
            port_bindings={5432: (LOCALHOST, None)},
            tmpfs=[postgresql_data_path],
        ),
        environment={
            "POSTGRES_HOST_AUTH_METHOD": "trust",
            "PGDATA": postgresql_data_path,
            "POSTGRES_INITDB_ARGS": "--no-sync",
        },
        command="-c fsync=off -c full_page_writes=off -c synchronous_commit=off -c bgwriter_lru_maxpages=0 -c jit=off",
    )

    try:
        docker_client.start(container=container["Id"])
        port = published_port(docker_client, container["Id"])

        started_at = time.monotonic()

        while time.monotonic() - started_at < ready_timeout:
            if is_pg_ready(
                host=LOCALHOST,
                port=port,
                database=DEFAULT_PG_DATABASE,
                user=DEFAULT_PG_USER,
                password=DEFAULT_PG_PASSWORD,
            ):
                break

            time.sleep(0.05)
        else:
            container_logs = docker_client.logs(container["Id"]).decode()
            pytest.fail(f"Failed to start postgres using {image} in {ready_timeout} seconds: {container_logs}")

        yield PG(
            host=LOCALHOST,
            port=port,
            user=DEFAULT_PG_USER,
            password=DEFAULT_PG_PASSWORD,
            database=DEFAULT_PG_DATABASE,
        )
    finally:
        # Force, and one call: a container that never started cannot be killed, and a teardown that
        # raises on that hides whatever went wrong with the start.
        docker_client.remove_container(container["Id"], v=True, force=True)


@pytest.fixture(scope="session")
def pg(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with run_pg(resolve_image(str(pytestconfig.getini("pg_docker_image_name")), "latest")) as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_14(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with run_pg(resolve_image(str(pytestconfig.getini("pg_docker_image_name")), "14")) as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_15(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with run_pg(resolve_image(str(pytestconfig.getini("pg_docker_image_name")), "15")) as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_16(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with run_pg(resolve_image(str(pytestconfig.getini("pg_docker_image_name")), "16")) as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_17(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with run_pg(resolve_image(str(pytestconfig.getini("pg_docker_image_name")), "17")) as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_18(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with run_pg(resolve_image(str(pytestconfig.getini("pg_docker_image_name")), "18")) as pg:
        yield pg
