.PHONY: all uv deps lint test

all: deps lint test

UV_EXTRA_ARGS ?=

uv:
	@which uv >/dev/null 2>&1 || { \
		echo "uv is not installed"; \
		exit 1;\
	}

deps: uv
	@uv sync --all-extras

lint: deps
ifeq ($(MODE), ci)
	@uv run $(UV_EXTRA_ARGS) ruff format pytest_pg tests --check
	@uv run $(UV_EXTRA_ARGS) ruff check pytest_pg tests
	@uv run $(UV_EXTRA_ARGS) pyright
else
	@uv run $(UV_EXTRA_ARGS) ruff format pytest_pg tests
	@uv run $(UV_EXTRA_ARGS) ruff check pytest_pg tests --fix
	@uv run $(UV_EXTRA_ARGS) pyright
endif

test: deps
	@uv run $(UV_EXTRA_ARGS) pytest -vv --rootdir tests .
