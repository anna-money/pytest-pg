import contextlib
import dataclasses
import datetime
import enum
import hashlib
import math
import os
import time
import uuid
from collections.abc import Callable, Generator

import docker
import docker.errors
import pytest

from .utils import find_unused_local_port, is_pg_ready, resolve_docker_host, resolve_image

LOCALHOST = "127.0.0.1"
DEFAULT_PG_USER = "postgres"
DEFAULT_PG_PASSWORD = "mysecretpassword"
DEFAULT_PG_DATABASE = "postgres"

POSTGRESQL_DATA_PATH = "/var/lib/postgresql/data"
PG_PORT = 5432
PG_ENVIRONMENT = {
    "POSTGRES_HOST_AUTH_METHOD": "trust",
    "PGDATA": POSTGRESQL_DATA_PATH,
    "POSTGRES_INITDB_ARGS": "--no-sync",
}
PG_COMMAND = "-c fsync=off -c full_page_writes=off -c synchronous_commit=off -c bgwriter_lru_maxpages=0 -c jit=off"

REUSE_NAME_PREFIX = "pytest-pg-reuse-"
DATABASE_NAME_PREFIX = "pytest_"
DEFAULT_DATABASE_MAX_AGE_DAYS = 2.0


@dataclasses.dataclass(frozen=True)
class PG:
    host: str
    port: int
    user: str
    password: str
    database: str


class PgMode(str, enum.Enum):
    EPHEMERAL = "ephemeral"
    REUSABLE = "reusable"


def _ensure_image(docker_client: docker.APIClient, image: str) -> None:
    try:
        docker_client.inspect_image(image)
    except docker.errors.ImageNotFound:
        docker_client.pull(image)


def _create_pg_container(docker_client: docker.APIClient, image: str, name: str, host_port: int) -> str:
    container_id = docker_client.create_container(
        image=image,
        name=name,
        ports=[PG_PORT],
        detach=True,
        host_config=docker_client.create_host_config(
            port_bindings={PG_PORT: (LOCALHOST, host_port)}, tmpfs=[POSTGRESQL_DATA_PATH]
        ),
        environment=PG_ENVIRONMENT,
        command=PG_COMMAND,
    )["Id"]

    try:
        docker_client.start(container=container_id)
    except docker.errors.APIError:
        with contextlib.suppress(docker.errors.APIError):
            docker_client.remove_container(container_id, v=True, force=True)
        raise

    return container_id


def _wait_until_ready(
    docker_client: docker.APIClient, reference: str, image: str, ready_timeout: float, is_ready: Callable[[], bool]
) -> None:
    started_at = time.monotonic()
    while time.monotonic() - started_at < ready_timeout:
        if is_ready():
            return
        time.sleep(0.05)
    try:
        container_logs = docker_client.logs(reference).decode()
    except docker.errors.APIError:
        container_logs = "<container logs unavailable>"
    pytest.fail(f"Failed to start postgres using {image} in {ready_timeout} seconds: {container_logs}")


@contextlib.contextmanager
def run_pg(image: str, ready_timeout: float = 30.0) -> Generator[PG, None, None]:
    docker_client = docker.APIClient(base_url=resolve_docker_host(), version="auto")

    _ensure_image(docker_client, image)
    unused_port = find_unused_local_port()
    container_id = _create_pg_container(docker_client, image, f"pytest-pg-{uuid.uuid4()}", unused_port)

    try:
        _wait_until_ready(
            docker_client,
            container_id,
            image,
            ready_timeout,
            lambda: is_pg_ready(
                host=LOCALHOST,
                port=unused_port,
                database=DEFAULT_PG_DATABASE,
                user=DEFAULT_PG_USER,
                password=DEFAULT_PG_PASSWORD,
            ),
        )

        yield PG(
            host=LOCALHOST,
            port=unused_port,
            user=DEFAULT_PG_USER,
            password=DEFAULT_PG_PASSWORD,
            database=DEFAULT_PG_DATABASE,
        )
    finally:
        docker_client.kill(container=container_id)
        docker_client.remove_container(container_id, v=True)


def _reuse_container_name(image: str, command: str, environment: dict[str, str]) -> str:
    version = image.rsplit(":", 1)[-1]
    spec = "\n".join([image, command, *(f"{key}={environment[key]}" for key in sorted(environment))])
    spec_hash = hashlib.blake2b(spec.encode(), digest_size=6).hexdigest()
    return f"{REUSE_NAME_PREFIX}{version}-{spec_hash}"


def _worker_database_name(worker_id: str) -> str:
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{DATABASE_NAME_PREFIX}{worker_id}_{timestamp}_{uuid.uuid4().hex[:8]}"


def _parse_database_timestamp(database: str) -> datetime.datetime | None:
    for part in database.split("_"):
        if len(part) == 14 and part.isdigit():
            try:
                return datetime.datetime.strptime(part, "%Y%m%d%H%M%S").replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                return None
    return None


def _is_stale(created_epoch: float, now_epoch: float, max_age: datetime.timedelta) -> bool:
    return now_epoch - created_epoch > max_age.total_seconds()


def _docker_exec(docker_client: docker.APIClient, container: str, command: list[str]) -> str:
    exec_id = docker_client.exec_create(container, command, user=DEFAULT_PG_USER)["Id"]
    stdout, stderr = docker_client.exec_start(exec_id, demux=True)
    exit_code = docker_client.exec_inspect(exec_id)["ExitCode"]
    if exit_code != 0:
        output = (stderr or stdout or b"").decode()
        raise RuntimeError(f"`{' '.join(command)}` failed with exit code {exit_code}: {output}")
    return (stdout or b"").decode()


def _drop_database(docker_client: docker.APIClient, container: str, database: str) -> None:
    _docker_exec(docker_client, container, ["dropdb", "--force", "--if-exists", "-U", DEFAULT_PG_USER, database])


def _is_pg_ready_in_container(docker_client: docker.APIClient, container: str) -> bool:
    try:
        _docker_exec(docker_client, container, ["pg_isready", "-q", "-h", "localhost"])
    except (RuntimeError, docker.errors.APIError):
        return False
    return True


def _reap_stale_reuse_databases(docker_client: docker.APIClient, container: str, max_age: datetime.timedelta) -> None:
    if max_age.total_seconds() <= 0:
        return
    try:
        listing = _docker_exec(
            docker_client,
            container,
            [
                "psql",
                "-U",
                DEFAULT_PG_USER,
                "-tAc",
                f"SELECT datname FROM pg_database WHERE starts_with(datname, '{DATABASE_NAME_PREFIX}')",
            ],
        )
    except (RuntimeError, docker.errors.APIError):
        return

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    for database in listing.split():
        created = _parse_database_timestamp(database)
        if created is None or not _is_stale(created.timestamp(), now, max_age):
            continue
        with contextlib.suppress(RuntimeError, docker.errors.APIError):
            _drop_database(docker_client, container, database)


def _ensure_reuse_container(docker_client: docker.APIClient, image: str, name: str) -> None:
    match = next(
        (
            container
            for container in docker_client.containers(all=True, filters={"name": name})
            if name in {candidate.lstrip("/") for candidate in container["Names"]}
        ),
        None,
    )
    if match is not None:
        if match["State"] not in {"exited", "dead"}:
            return
        try:
            docker_client.remove_container(match["Id"], v=True, force=True)
        except docker.errors.APIError as error:
            if error.status_code not in (404, 409):
                raise

    _ensure_image(docker_client, image)
    try:
        _create_pg_container(docker_client, image, name, find_unused_local_port())
    except docker.errors.APIError as error:
        if error.status_code != 409:
            raise


def _ensure_running_reuse_container(
    docker_client: docker.APIClient, image: str, name: str, ready_timeout: float
) -> int:
    last_error: Exception = RuntimeError(f"could not obtain a running reusable container {name}")
    for _ in range(2):
        _ensure_reuse_container(docker_client, image, name)
        _wait_until_ready(
            docker_client, name, image, ready_timeout, lambda: _is_pg_ready_in_container(docker_client, name)
        )
        try:
            ports = docker_client.inspect_container(name)["NetworkSettings"]["Ports"]
            return int(ports[f"{PG_PORT}/tcp"][0]["HostPort"])
        except docker.errors.NotFound as error:
            last_error = error
    raise last_error


@contextlib.contextmanager
def run_reusable_pg(
    image: str, ready_timeout: float = 30.0, database_max_age_days: float = DEFAULT_DATABASE_MAX_AGE_DAYS
) -> Generator[PG, None, None]:
    docker_client = docker.APIClient(base_url=resolve_docker_host(), version="auto")
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    name = _reuse_container_name(image, PG_COMMAND, PG_ENVIRONMENT)

    host_port = _ensure_running_reuse_container(docker_client, image, name, ready_timeout)

    if worker_id in {"master", "gw0"}:
        _reap_stale_reuse_databases(docker_client, name, datetime.timedelta(days=database_max_age_days))

    database = _worker_database_name(worker_id)
    _docker_exec(docker_client, name, ["createdb", "-U", DEFAULT_PG_USER, database])

    try:
        yield PG(
            host=LOCALHOST,
            port=host_port,
            user=DEFAULT_PG_USER,
            password=DEFAULT_PG_PASSWORD,
            database=database,
        )
    finally:
        with contextlib.suppress(RuntimeError, docker.errors.APIError):
            _drop_database(docker_client, name, database)


def _resolve_pg_mode(pytestconfig: pytest.Config) -> PgMode:
    value = str(pytestconfig.getini("pg_mode"))
    try:
        return PgMode(value)
    except ValueError:
        raise pytest.UsageError(
            f"Invalid pg_mode {value!r}; expected one of {[mode.value for mode in PgMode]}"
        ) from None


def _resolve_database_max_age_days(pytestconfig: pytest.Config) -> float:
    value = str(pytestconfig.getini("pg_database_max_age_days"))
    try:
        days = float(value)
    except ValueError:
        raise pytest.UsageError(f"Invalid pg_database_max_age_days {value!r}; expected a number of days") from None
    if not math.isfinite(days) or days <= 0:
        raise pytest.UsageError(f"Invalid pg_database_max_age_days {value!r}; expected a positive number of days")
    return days


@contextlib.contextmanager
def _session_pg(pytestconfig: pytest.Config, version: str) -> Generator[PG, None, None]:
    image = resolve_image(str(pytestconfig.getini("pg_docker_image_name")), version)
    match _resolve_pg_mode(pytestconfig):
        case PgMode.EPHEMERAL:
            context = run_pg(image)
        case PgMode.REUSABLE:
            context = run_reusable_pg(image, database_max_age_days=_resolve_database_max_age_days(pytestconfig))
    with context as pg:
        yield pg


@pytest.fixture(scope="session")
def pg(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _session_pg(pytestconfig, "latest") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_14(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _session_pg(pytestconfig, "14") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_15(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _session_pg(pytestconfig, "15") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_16(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _session_pg(pytestconfig, "16") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_17(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _session_pg(pytestconfig, "17") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_18(pytestconfig: pytest.Config) -> Generator[PG, None, None]:
    with _session_pg(pytestconfig, "18") as pg:
        yield pg
