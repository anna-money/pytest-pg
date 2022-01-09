import contextlib
import dataclasses
import time
import uuid
from typing import Generator

import docker
import pytest

from .utils import find_unused_local_port, is_pg_ready

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
    docker_client = docker.APIClient(version="auto")

    docker_client.pull(image)

    unused_port = find_unused_local_port()

    postgresql_data_path = "/var/lib/postgresql/data"

    container = docker_client.create_container(
        image=image,
        name=f"pytest-pg-{uuid.uuid4()}",
        ports=[5432],
        detach=True,
        host_config=docker_client.create_host_config(
            port_bindings={5432: (LOCALHOST, unused_port)}, tmpfs=[postgresql_data_path]
        ),
        environment={"POSTGRES_HOST_AUTH_METHOD": "trust", "PGDATA": postgresql_data_path},
        command="-c fsync=off -c full_page_writes=off -c synchronous_commit=off",
    )

    try:
        docker_client.start(container=container["Id"])

        started_at = time.time()

        while time.time() - started_at < ready_timeout:
            if is_pg_ready(
                host=LOCALHOST,
                port=unused_port,
                database=DEFAULT_PG_DATABASE,
                user=DEFAULT_PG_USER,
                password=DEFAULT_PG_PASSWORD,
            ):
                break

            time.sleep(0.5)
        else:
            pytest.fail(f"Failed to start postgres using {image} in {ready_timeout} seconds")

        yield PG(
            host=LOCALHOST,
            port=unused_port,
            user=DEFAULT_PG_USER,
            password=DEFAULT_PG_PASSWORD,
            database=DEFAULT_PG_DATABASE,
        )
    finally:
        docker_client.kill(container=container["Id"])
        docker_client.remove_container(container["Id"], v=True)


@pytest.fixture(scope="session")
def pg() -> Generator[PG, None, None]:
    with run_pg("postgres:latest") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_11() -> Generator[PG, None, None]:
    with run_pg("postgres:11") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_12() -> Generator[PG, None, None]:
    with run_pg("postgres:12") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_13() -> Generator[PG, None, None]:
    with run_pg("postgres:13") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_14() -> Generator[PG, None, None]:
    with run_pg("postgres:14") as pg:
        yield pg
