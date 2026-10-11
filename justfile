set windows-shell := ["cmd.exe", "/c"]

PYTHON := if os_family() == "windows" { ".venv/Scripts/python.exe" } else { ".venv/bin/python" }
UI := "kaleidoscope/ui"

default:
    @just --list

build-ui:
    bun run --cwd {{UI}} build

coverage:
    {{PYTHON}} -m pytest --cov=kaleidoscope --cov-report=term-missing
    bun run --cwd {{UI}} test:coverage

install:
    uv venv --python 3.13 --allow-existing .venv
    uv pip install --python {{PYTHON}} -e ".[dev]"
    {{PYTHON}} -m playwright install chromium
    bun install --cwd {{UI}}

lint:
    {{PYTHON}} -m ruff check .
    {{PYTHON}} -m ty check kaleidoscope

lint-ui:
    bun run --cwd {{UI}} lint
    bun run --cwd {{UI}} typecheck

migrate:
    {{PYTHON}} example/manage.py migrate

[unix]
reset:
    rm -f example/database.sqlite3
    just migrate
    just seed

[windows]
reset:
    if exist example\database.sqlite3 del /q example\database.sqlite3
    just migrate
    just seed

run-server:
    {{PYTHON}} example/manage.py runserver 127.0.0.1:8765

screenshot *FILTER:
    {{PYTHON}} example/capture.py {{FILTER}}

seed:
    {{PYTHON}} example/manage.py seed

shell:
    {{PYTHON}} example/manage.py shell

test:
    {{PYTHON}} -m pytest

test-all: test test-fuzz test-simulation test-packaging test-e2e test-ui test-ui-fuzz test-ui-simulation

test-e2e:
    {{PYTHON}} -m pytest -m e2e

test-fuzz $FUZZ_CASES="1000":
    {{PYTHON}} -m pytest -m fuzz

test-packaging:
    {{PYTHON}} -m pytest -m packaging

test-simulation $SIMULATION_SEED_COUNT="40":
    {{PYTHON}} -m pytest -m simulation

test-ui:
    bun run --cwd {{UI}} test

test-ui-fuzz $FUZZ_CASES="2000":
    bun run --cwd {{UI}} test tests/fuzz

test-ui-simulation $SIMULATION_SEED_COUNT="40":
    bun run --cwd {{UI}} test tests/simulation
