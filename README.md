# pytest-pg

A pytest plugin that provides session-scoped fixtures for running PostgreSQL inside Docker containers.
It automatically spins up a container, waits for PostgreSQL to become ready, exposes connection details
(`host`, `port`, `user`, `password`, `database`) via a `PG` dataclass, and tears the container down after
the test session. Pre-built fixtures are available for PostgreSQL versions 14 through 18 as well as `latest`.

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


# Reusable container mode

By default each test session spins up a fresh container and removes it at the end (`ephemeral` mode). Set
`pg_mode = "reusable"` to instead keep a **long-living** container alive across runs and allocate a **fresh
database per session** (one per xdist worker) inside it. Container startup is then paid once; subsequent runs
only pay a near-instant `CREATE DATABASE`.

```toml
[tool.pytest.ini_options]
pg_mode = "reusable"
```

Or per run, without committing it:

```
pytest -o pg_mode=reusable
```

In reusable mode:

* the container is named `pytest-pg-reuse-<version>-<hash>` and is **never** torn down — later runs reuse it
  (remove it with `docker rm -f pytest-pg-reuse-*` to reclaim it or to pick up a newer image of the same tag);
* every fixture (`pg`, `pg_14` … `pg_18`) yields a connection to its own freshly-created database, dropped at
  the end of the session;
* under `pytest -n` (xdist) all workers share one container, each with its own database;
* leftover databases from previous runs are dropped once they are older than `pg_reusable_db_max_age_days`
  (default `2`), which bounds the memory used by the long-living container.

```toml
[tool.pytest.ini_options]
pg_mode = "reusable"
pg_reusable_db_max_age_days = 2
```

The `run_reusable_pg` context manager is the building block behind these fixtures, mirroring `run_pg`:

```python
import pytest_pg


with pytest_pg.run_reusable_pg("postgres:18") as pg:
    ...
```


# Using a custom registry

By default the built-in fixtures pull `postgres:<version>` from Docker Hub. To pull from a mirror
instead (for example, to avoid Docker Hub rate limits), set the base image in `pyproject.toml`. The
fixtures append the version tag to it, so the mirror must carry the matching tags: `<base>:14` …
`<base>:18` for the versioned fixtures, and `<base>:latest` for the `pg` fixture. Mirrors of pinned
versions often omit `latest`; if yours does, use a versioned `pg_NN` fixture instead of `pg`.

```toml
[tool.pytest.ini_options]
pg_docker_image_name = "eu.gcr.io/anna-money/postgres"
```
