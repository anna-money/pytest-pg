import socket
import subprocess
from typing import Any
from unittest import mock

from pytest_pg.utils import find_unused_local_port, is_local_port_open, resolve_docker_host, resolve_image


def test_resolve_docker_host_returns_env_when_set(monkeypatch: Any) -> None:
    monkeypatch.setenv("DOCKER_HOST", "tcp://example:2375")
    with mock.patch("pytest_pg.utils.subprocess.run") as run:
        assert resolve_docker_host() == "tcp://example:2375"
    run.assert_not_called()


def test_resolve_docker_host_returns_none_when_cli_missing(monkeypatch: Any) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    with mock.patch("pytest_pg.utils.shutil.which", return_value=None):
        assert resolve_docker_host() is None


def test_resolve_docker_host_reads_active_context(monkeypatch: Any) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="unix:///tmp/colima.sock\n", stderr="")
    with (
        mock.patch("pytest_pg.utils.shutil.which", return_value="/usr/bin/docker"),
        mock.patch("pytest_pg.utils.subprocess.run", return_value=completed) as run,
    ):
        assert resolve_docker_host() == "unix:///tmp/colima.sock"
    args, _ = run.call_args
    assert args[0] == ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]


def test_resolve_docker_host_returns_none_on_empty_output(monkeypatch: Any) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="\n", stderr="")
    with (
        mock.patch("pytest_pg.utils.shutil.which", return_value="/usr/bin/docker"),
        mock.patch("pytest_pg.utils.subprocess.run", return_value=completed),
    ):
        assert resolve_docker_host() is None


def test_resolve_docker_host_returns_none_on_cli_error(monkeypatch: Any) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    err = subprocess.CalledProcessError(returncode=1, cmd=["docker"])
    with (
        mock.patch("pytest_pg.utils.shutil.which", return_value="/usr/bin/docker"),
        mock.patch("pytest_pg.utils.subprocess.run", side_effect=err),
    ):
        assert resolve_docker_host() is None


def test_resolve_docker_host_returns_none_on_timeout(monkeypatch: Any) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    err = subprocess.TimeoutExpired(cmd=["docker"], timeout=5)
    with (
        mock.patch("pytest_pg.utils.shutil.which", return_value="/usr/bin/docker"),
        mock.patch("pytest_pg.utils.subprocess.run", side_effect=err),
    ):
        assert resolve_docker_host() is None


def test_resolve_image_uses_default_base() -> None:
    assert resolve_image("postgres", "14") == "postgres:14"


def test_resolve_image_uses_configured_base() -> None:
    assert resolve_image("eu.gcr.io/anna-money/postgres", "14") == "eu.gcr.io/anna-money/postgres:14"


def test_is_local_port_open_true_for_listening_socket() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        assert is_local_port_open("127.0.0.1", server.getsockname()[1]) is True


def test_is_local_port_open_false_for_unbound_port() -> None:
    assert is_local_port_open("127.0.0.1", find_unused_local_port()) is False
