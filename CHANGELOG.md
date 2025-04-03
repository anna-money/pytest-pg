## v0.0.22 (2025-04-03)

* Override docker host with env variable


## v0.0.17 (2024-04-03)

* Override docker host with env variable


## v0.0.15 (2023-05-04)

* Pin version of `urllib3` ([see for more details](https://github.com/docker/docker-py/issues/3113))
* Add `pg_15` fixture


## v0.0.14 (2022-09-19)

* Disable jit by default
* Set bgwriter_lru_maxpages


## v0.0.12 (2022-01-18)

* Ditch logging because it seems to be useless


## v0.0.11 (2022-01-09)

* Move volume to tmpfs


## v0.0.10 (2022-01-08)

* Volumes used to remain after running test consuming disk space


## v0.0.9 (2021-12-28)

* Disable fsync, full_page_writes, synchronous_commit to speedup the tests


## v0.0.8 (2021-12-26)

* Add typing marker, mypy. Run tests in CI


## v0.0.7 (2021-12-25)

* Fix is_ready based on psycopg2


## v0.0.6 (2021-12-25)

* Add all recent major versions of PG


## v0.0.4 (2021-12-10)

* Fix is_postgres_ready usage

## v0.0.3 (2021-12-10)

* Fix uuid generation

## v0.0.2 (2021-12-10)

* Follow pytest guide for plugins

## v0.0.1 (2021-12-10)

* A first version
