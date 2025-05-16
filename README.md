To speed up tests, pytest-pg does the following tweaks:

1. fsync=off
1. full_page_writes=off
1. synchronous_commit=off
1. jit=off
1. bgwriter_lru_maxpages=0
1. Mounts data directory to a tmpfs 

# How to use?

```
import os
import asyncio
import asyncpg

import pytest

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
