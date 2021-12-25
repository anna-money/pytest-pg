import contextlib
import dataclasses
import time
import uuid

import docker
import pytest

from .utils import find_unused_local_port, is_pg_ready

LOCALHOST = "127.0.0.1"

DEFAULT_PG_USER = "postgres"
DEFAULT_PG_PASSWORD = "mysecretpassword"
DEFAULT_PG_DATABASE = "postgres"


@dataclasses.dataclass(frozen=True)
class PostgresCredentials:
    host: str
    port: int
    user: str
    password: str
    database: str


@contextlib.contextmanager
def run_pg(image, ready_timeout=30.0):
    docker_client = docker.APIClient(version="auto")

    docker_client.pull(image)

    unused_port = find_unused_local_port()

    container = docker_client.create_container(
        image=image,
        name=f"pytest-pg-{uuid.uuid4()}",
        ports=[5432],
        detach=True,
        host_config=docker_client.create_host_config(port_bindings={5432: (LOCALHOST, unused_port)}),
        environment={"POSTGRES_HOST_AUTH_METHOD": "trust"},
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

            time.sleep(500)
        else:
            raise Exception("Failed to start postgres")

        yield PostgresCredentials(
            host=LOCALHOST,
            port=unused_port,
            user=DEFAULT_PG_USER,
            password=DEFAULT_PG_PASSWORD,
            database=DEFAULT_PG_DATABASE,
        )
    finally:
        docker_client.kill(container=container["Id"])
        docker_client.remove_container(container["Id"])


@pytest.fixture(scope="session")
def pg():
    with run_pg("postgres:latest") as credentials:
        yield credentials


@pytest.fixture(scope="session")
def pg_11():
    with run_pg("postgres:11") as credentials:
        yield credentials


@pytest.fixture(scope="session")
def pg_12():
    with run_pg("postgres:12") as credentials:
        yield credentials


@pytest.fixture(scope="session")
def pg_13():
    with run_pg("postgres:13") as credentials:
        yield credentials


@pytest.fixture(scope="session")
def pg_14():
    with run_pg("postgres:14") as credentials:
        yield credentials
