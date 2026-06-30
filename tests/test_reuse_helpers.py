# pyright: reportPrivateUsage=false
import datetime
import re
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

import docker.errors
import pytest

from pytest_pg.fixtures import (
    PG_COMMAND,
    PG_ENVIRONMENT,
    PgMode,
    _drop_database,
    _ensure_reuse_container,
    _ensure_running_reuse_container,
    _image_tag,
    _is_stale,
    _parse_database_timestamp,
    _resolve_database_max_age_days,
    _resolve_pg_mode,
    _reuse_container_name,
    _worker_database_name,
)


def test_reuse_container_name_format() -> None:
    name = _reuse_container_name("postgres:16", PG_COMMAND, PG_ENVIRONMENT)
    assert re.fullmatch(r"pytest-pg-reuse-16-[0-9a-f]{12}", name)


def test_reuse_container_name_is_deterministic() -> None:
    assert _reuse_container_name("postgres:16", PG_COMMAND, PG_ENVIRONMENT) == _reuse_container_name(
        "postgres:16", PG_COMMAND, PG_ENVIRONMENT
    )


def test_reuse_container_name_differs_by_image() -> None:
    assert _reuse_container_name("postgres:16", PG_COMMAND, PG_ENVIRONMENT) != _reuse_container_name(
        "registry.example/postgres:16", PG_COMMAND, PG_ENVIRONMENT
    )


def test_reuse_container_name_differs_by_command() -> None:
    assert _reuse_container_name("postgres:16", PG_COMMAND, PG_ENVIRONMENT) != _reuse_container_name(
        "postgres:16", PG_COMMAND + " -c work_mem=8MB", PG_ENVIRONMENT
    )


def test_reuse_container_name_differs_by_environment() -> None:
    assert _reuse_container_name("postgres:16", PG_COMMAND, PG_ENVIRONMENT) != _reuse_container_name(
        "postgres:16", PG_COMMAND, {**PG_ENVIRONMENT, "PGDATA": "/other"}
    )


def test_reuse_container_name_is_valid_for_registry_port_image() -> None:
    name = _reuse_container_name("myregistry:5000/postgres", PG_COMMAND, PG_ENVIRONMENT)
    assert re.fullmatch(r"pytest-pg-reuse-latest-[0-9a-f]{12}", name)


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("postgres", "latest"),
        ("postgres:16", "16"),
        ("myregistry:5000/postgres", "latest"),
        ("myregistry:5000/postgres:16", "16"),
        ("ns/repo:18", "18"),
    ],
)
def test_image_tag(image: str, expected: str) -> None:
    assert _image_tag(image) == expected


def test_worker_database_name_format() -> None:
    name = _worker_database_name("gw0")
    assert re.fullmatch(r"pytest_gw0_\d{14}_[0-9a-f]{8}", name)
    assert name[0].isalpha()
    assert name == name.lower()
    assert len(name) <= 63


def test_worker_database_name_is_unique() -> None:
    assert _worker_database_name("gw0") != _worker_database_name("gw0")


def test_parse_database_timestamp_round_trips() -> None:
    parsed = _parse_database_timestamp(_worker_database_name("gw3"))
    assert parsed is not None
    assert parsed.tzinfo is datetime.timezone.utc
    assert abs((datetime.datetime.now(datetime.timezone.utc) - parsed).total_seconds()) < 60


@pytest.mark.parametrize(
    "database",
    ["postgres", "template0", "template1", "pytest_master", "pytest_gw0_notatimestamp_ab"],
)
def test_parse_database_timestamp_returns_none_without_timestamp(database: str) -> None:
    assert _parse_database_timestamp(database) is None


def test_parse_database_timestamp_returns_none_for_invalid_calendar() -> None:
    assert _parse_database_timestamp("pytest_gw0_99999999999999_abcd1234") is None


def test_is_stale_boundary() -> None:
    max_age = datetime.timedelta(days=2)
    now = 1_000_000.0
    assert _is_stale(now - max_age.total_seconds() - 1, now, max_age) is True
    assert _is_stale(now - max_age.total_seconds(), now, max_age) is False
    assert _is_stale(now - 10, now, max_age) is False


def _stub_config(values: dict[str, str]) -> Any:
    return SimpleNamespace(getini=lambda name: values[name])


def test_resolve_pg_mode_valid() -> None:
    assert _resolve_pg_mode(_stub_config({"pg_mode": "ephemeral"})) is PgMode.EPHEMERAL
    assert _resolve_pg_mode(_stub_config({"pg_mode": "reusable"})) is PgMode.REUSABLE


def test_resolve_pg_mode_invalid() -> None:
    with pytest.raises(pytest.UsageError):
        _resolve_pg_mode(_stub_config({"pg_mode": "bogus"}))


def test_resolve_database_max_age_days_valid() -> None:
    assert _resolve_database_max_age_days(_stub_config({"pg_reusable_db_max_age_days": "2"})) == 2.0
    assert _resolve_database_max_age_days(_stub_config({"pg_reusable_db_max_age_days": "0.5"})) == 0.5


@pytest.mark.parametrize("value", ["soon", "0", "-1", "nan", "inf"])
def test_resolve_database_max_age_days_invalid(value: str) -> None:
    with pytest.raises(pytest.UsageError):
        _resolve_database_max_age_days(_stub_config({"pg_reusable_db_max_age_days": value}))


def _stub_client(containers: list[dict[str, Any]]) -> Any:
    client = mock.MagicMock()
    client.containers.return_value = containers
    return client


def _api_error(status_code: int) -> docker.errors.APIError:
    return docker.errors.APIError("boom", response=cast(Any, SimpleNamespace(status_code=status_code)))


def test_ensure_reuse_container_reuses_running() -> None:
    client = _stub_client([{"Names": ["/the-name"], "State": "running", "Id": "id1"}])
    with mock.patch("pytest_pg.fixtures._create_pg_container") as create:
        _ensure_reuse_container(client, "postgres:16", "the-name")
    create.assert_not_called()
    client.remove_container.assert_not_called()


def test_ensure_reuse_container_creates_when_absent() -> None:
    client = _stub_client([])
    with (
        mock.patch("pytest_pg.fixtures._create_pg_container") as create,
        mock.patch("pytest_pg.fixtures.find_unused_local_port", return_value=5555),
    ):
        _ensure_reuse_container(client, "postgres:16", "the-name")
    create.assert_called_once_with(client, "postgres:16", "the-name", 5555)


@pytest.mark.parametrize("state", ["exited", "dead"])
def test_ensure_reuse_container_recreates_terminal(state: str) -> None:
    client = _stub_client([{"Names": ["/the-name"], "State": state, "Id": "id1"}])
    with (
        mock.patch("pytest_pg.fixtures._create_pg_container") as create,
        mock.patch("pytest_pg.fixtures.find_unused_local_port", return_value=5555),
    ):
        _ensure_reuse_container(client, "postgres:16", "the-name")
    client.remove_container.assert_called_once()
    create.assert_called_once()


@pytest.mark.parametrize("state", ["created", "restarting", "paused"])
def test_ensure_reuse_container_leaves_transient_state(state: str) -> None:
    client = _stub_client([{"Names": ["/the-name"], "State": state, "Id": "id1"}])
    with mock.patch("pytest_pg.fixtures._create_pg_container") as create:
        _ensure_reuse_container(client, "postgres:16", "the-name")
    create.assert_not_called()
    client.remove_container.assert_not_called()


def test_ensure_running_reuse_container_recreates_after_timeout() -> None:
    client = mock.MagicMock()
    with (
        mock.patch("pytest_pg.fixtures._ensure_reuse_container"),
        mock.patch("pytest_pg.fixtures._resolve_ready_host_port", side_effect=[None, 5432]),
    ):
        assert _ensure_running_reuse_container(client, "postgres:16", "the-name", 0.1) == 5432
    client.remove_container.assert_called_once()


def test_ensure_reuse_container_swallows_create_conflict() -> None:
    client = _stub_client([])
    with (
        mock.patch("pytest_pg.fixtures._create_pg_container", side_effect=_api_error(409)),
        mock.patch("pytest_pg.fixtures.find_unused_local_port", return_value=5555),
    ):
        _ensure_reuse_container(client, "postgres:16", "the-name")


def test_ensure_reuse_container_reraises_other_create_errors() -> None:
    client = _stub_client([])
    with (
        mock.patch("pytest_pg.fixtures._create_pg_container", side_effect=_api_error(500)),
        mock.patch("pytest_pg.fixtures.find_unused_local_port", return_value=5555),
        pytest.raises(docker.errors.APIError),
    ):
        _ensure_reuse_container(client, "postgres:16", "the-name")


def test_drop_database_omits_force_by_default() -> None:
    with mock.patch("pytest_pg.fixtures._docker_exec") as docker_exec:
        _drop_database(mock.MagicMock(), "the-name", "db")
    assert "--force" not in docker_exec.call_args.args[2]


def test_drop_database_includes_force_when_requested() -> None:
    with mock.patch("pytest_pg.fixtures._docker_exec") as docker_exec:
        _drop_database(mock.MagicMock(), "the-name", "db", force=True)
    assert "--force" in docker_exec.call_args.args[2]
