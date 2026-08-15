set windows-shell := ["cmd.exe", "/c"]

PYTHON := if os() == "linux" { ".venv/bin/python" } else { ".venv/Scripts/python.exe" }

default:
    @just --list

install:
    uv venv --python 3.13 --allow-existing .venv
    uv pip install --python {{PYTHON}} -e ".[dev]"
    {{PYTHON}} -m playwright install chromium

lint:
    {{PYTHON}} -m ruff check .

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
