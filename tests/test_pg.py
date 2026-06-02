import pytest_pg


def test_pg(pg: pytest_pg.PG) -> None:
    assert pg


def test_pg_14(pg_14: pytest_pg.PG) -> None:
    assert pg_14


def test_pg_15(pg_15: pytest_pg.PG) -> None:
    assert pg_15


def test_pg_16(pg_16: pytest_pg.PG) -> None:
    assert pg_16


def test_pg_17(pg_17: pytest_pg.PG) -> None:
    assert pg_17


def test_pg_18(pg_18: pytest_pg.PG) -> None:
    assert pg_18
