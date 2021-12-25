from pytest_pg.plugin import run_pg


def test_run_pg():
    with run_pg("postgres"):
        pass
