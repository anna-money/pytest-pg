# pytest-pg

A pytest plugin that provides session-scoped fixtures for running PostgreSQL inside Docker containers.
It automatically spins up a container, waits for PostgreSQL to become ready, exposes connection details
(`host`, `port`, `user`, `password`, `database`) via a `PG` dataclass, and tears the container down after
the test session. Pre-built fixtures are available for PostgreSQL versions 11 through 18 as well as `latest`.

Readiness checks work with any of the common drivers — asyncpg, psycopg2, or psycopg3.

To speed up tests, pytest-pg does the following tweaks:

1. fsync=off
2. full_page_writes=off
3. synchronous_commit=off
4. jit=off
5. bgwriter_lru_maxpages=0
6. data directory is mounted to a tmpfs 


# How to use?

You can use the following fixtures:

* `pg` – the latest PostgreSQL image available
* `pg_11` – PostgreSQL 11
* `pg_12` – PostgreSQL 12
* `pg_13` – PostgreSQL 13
* `pg_14` – PostgreSQL 14
* `pg_15` – PostgreSQL 15
* `pg_16` – PostgreSQL 16
* `pg_17` – PostgreSQL 17
* `pg_18` – PostgreSQL 18

```python
import asyncpg


async def test_asyncpg_query(pg):
    conn = await asyncpg.connect(
        user=pg.user,
        password=pg.password,
        database=pg.database,
        host=pg.host,
        port=pg.port,
    )

    await conn.execute("CREATE TABLE test_table (id serial PRIMARY KEY, value text);")
    await conn.execute("INSERT INTO test_table (value) VALUES ($1)", "hello")
    row = await conn.fetchrow("SELECT value FROM test_table WHERE id = $1", 1)

    assert row["value"] == "hello"

    await conn.close()
```


Also `run_pg` context manager is available, you can use it to create your own fixture, using docker image you need:

```python
import os

import pytest
import pytest_pg


@pytest.fixture(scope='session', autouse=True)
def postgres_env_vars() -> Generator[None]:
    docker_image = 'postgres:18'
    with pytest_pg.run_pg(docker_image) as pg:
        os.environ['POSTGRES_USER'] = pg.user
        os.environ['POSTGRES_PASSWORD'] = pg.password
        os.environ['POSTGRES_HOST'] = pg.host
        os.environ['POSTGRES_PORT'] = str(pg.port)
        os.environ['POSTGRES_DBNAME'] = pg.database
        yield


# or like so:
@pytest.fixture(scope='session', autouse=True)
def postgres_env_vars(pg_18: pytest_pg.PG) -> Generator[None]:
    os.environ['POSTGRES_USER'] = pg_18.user
    os.environ['POSTGRES_PASSWORD'] = pg_18.password
    os.environ['POSTGRES_HOST'] = pg_18.host
    os.environ['POSTGRES_PORT'] = str(pg_18.port)
    os.environ['POSTGRES_DBNAME'] = pg_18.database
    yield
```
