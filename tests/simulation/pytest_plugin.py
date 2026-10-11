from __future__ import annotations

import os

import pytest

from tests.simulation.exceptions import SimulationBoundsError
from tests.simulation.run import SEED_MAX, STEP_COUNT_MAX


ENVIRONMENT_SEED_COUNT = 'SIMULATION_SEED_COUNT'
ENVIRONMENT_SEED_START = 'SIMULATION_SEED_START'
ENVIRONMENT_SEEDS = 'SIMULATION_SEEDS'
ENVIRONMENT_STEP_COUNT = 'SIMULATION_STEP_COUNT'
SEED_COUNT_DEFAULT = 1
SEED_COUNT_MAX = 100_000
SEED_FIXTURE_NAME = 'simulation_seed'
STEP_COUNT_DEFAULT = 300


def _environment_integer(name: str, *, default: int, value_max: int) -> int:
    raw = os.environ.get(name, '').strip()

    if not raw:
        return default

    if not raw.isascii():
        message = f'{name} must be a non-negative integer: {raw!r}'
        raise SimulationBoundsError(message)

    if not raw.isdigit():
        message = f'{name} must be a non-negative integer: {raw!r}'
        raise SimulationBoundsError(message)

    value = int(raw)

    if value > value_max:
        message = f'{name} exceeds {value_max}: {value}'
        raise SimulationBoundsError(message)

    return value


def _seed_parse(raw: str) -> int:
    text = raw.strip()

    if not text.isascii():
        message = f'{ENVIRONMENT_SEEDS} entry must be a non-negative integer: {raw!r}'
        raise SimulationBoundsError(message)

    if not text.isdigit():
        message = f'{ENVIRONMENT_SEEDS} entry must be a non-negative integer: {raw!r}'
        raise SimulationBoundsError(message)

    seed = int(text)

    if seed > SEED_MAX:
        message = f'{ENVIRONMENT_SEEDS} entry exceeds {SEED_MAX}: {seed}'
        raise SimulationBoundsError(message)

    return seed


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if SEED_FIXTURE_NAME in getattr(item, 'fixturenames', ()):
            item.add_marker(pytest.mark.simulation)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if SEED_FIXTURE_NAME not in metafunc.fixturenames:
        return

    metafunc.parametrize(SEED_FIXTURE_NAME, seeds_from_environment())


def seeds_from_environment() -> list[int]:
    seeds_raw = os.environ.get(ENVIRONMENT_SEEDS, '').strip()

    if seeds_raw:
        seeds = [_seed_parse(part) for part in seeds_raw.split(',')]
    else:
        start = _environment_integer(ENVIRONMENT_SEED_START, default=0, value_max=SEED_MAX)

        count = _environment_integer(
            ENVIRONMENT_SEED_COUNT,
            default=SEED_COUNT_DEFAULT,
            value_max=SEED_COUNT_MAX,
        )

        seeds = list(range(start, start + count))

    if not seeds:
        message = 'no simulation seeds selected'
        raise SimulationBoundsError(message)

    if len(seeds) > SEED_COUNT_MAX:
        message = f'seed count exceeds {SEED_COUNT_MAX}: {len(seeds)}'
        raise SimulationBoundsError(message)

    return seeds


def step_count_from_environment() -> int:
    return _environment_integer(
        ENVIRONMENT_STEP_COUNT,
        default=STEP_COUNT_DEFAULT,
        value_max=STEP_COUNT_MAX,
    )
