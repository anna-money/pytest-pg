import asyncio
import socket
import time
import uuid

import docker
import pytest


def _unused_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


try:
    import psycopg2

    def is_postgres_ready(**params):
        try:
            with psycopg2.connect(**params):
                return True
        except psycopg2.Error:
            return False


except ImportError:
    try:
        import asyncpg

        def is_postgres_ready(**params):
            async def _is_postgres_ready():
                try:
                    async with await asyncpg.connect(**params):
                        return True
                except (asyncpg.exceptions.PostgresError, OSError):
                    return False

            return asyncio.run(_is_postgres_ready())

    except ImportError:
        raise RuntimeError("Failed to load any supported postgres drivers")


@pytest.fixture(scope="session")
def postgres():
    docker_client = docker.APIClient(version="auto")

    docker_client.pull("postgres")

    container_args = dict(
        image="postgres",
        name=str(uuid.uuid4()),
        ports=[5432],
        detach=True,
    )

    # bound IPs do not work on OSX
    host = "127.0.0.1"
    port = _unused_port()
    container_args["host_config"] = docker_client.create_host_config(port_bindings={5432: (host, port)})
    container_args["environment"] = {"POSTGRES_HOST_AUTH_METHOD": "trust"}

    container = docker_client.create_container(**container_args)

    try:
        docker_client.start(container=container["Id"])
        delay = 0.001
        params = dict(database="postgres", user="postgres", password="mysecretpassword", host=host, port=port)

        for i in range(32):
            if is_postgres_ready(**params):
                break

            time.sleep(delay)
            delay *= 2
        else:
            pytest.fail("Cannot start postgres")

        yield params
    finally:
        docker_client.kill(container=container["Id"])
        docker_client.remove_container(container["Id"])
