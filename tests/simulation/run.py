from __future__ import annotations

import random

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tests.simulation.exceptions import (
    SimulationBoundsError,
    SimulationFailureError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


    Action = Callable[['Run'], None]
    Invariant = Callable[['Run'], None]


JOURNAL_LINES_MAX = 100_000
JOURNAL_TAIL_LINES = 40
SEED_MAX = 2**63 - 1
SOMETIMES_NAMES_MAX = 1000
STEP_COUNT_MAX = 1_000_000


def _journal_build() -> deque[str]:
    return deque(maxlen=JOURNAL_LINES_MAX)


@dataclass
class Run:
    rng: random.Random
    seed: int
    journal: deque[str] = field(default_factory=_journal_build)
    sometimes_counts: dict[str, int] = field(default_factory=dict)
    step: int = 0

    def journal_tail(self) -> list[str]:
        return list(self.journal)[-JOURNAL_TAIL_LINES:]

    def log(self, message: str) -> None:
        self.journal.append(f'step {self.step}: {message}')

    def sometimes(self, name: str, *, condition: bool = True) -> None:
        if name not in self.sometimes_counts:
            if len(self.sometimes_counts) >= SOMETIMES_NAMES_MAX:
                message = f'sometimes names exceed {SOMETIMES_NAMES_MAX}: {name!r}'
                raise SimulationBoundsError(message)

            self.sometimes_counts[name] = 0

        if condition:
            self.sometimes_counts[name] += 1

    def sometimes_unreached(self) -> list[str]:
        return sorted(name for name, count in self.sometimes_counts.items() if count == 0)


def _bounds_validate(name: str, value: int, *, value_min: int, value_max: int) -> None:
    if value < value_min:
        message = f'{name} must be within {value_min}..{value_max}: {value}'
        raise SimulationBoundsError(message)

    if value > value_max:
        message = f'{name} must be within {value_min}..{value_max}: {value}'
        raise SimulationBoundsError(message)


def _callable_name(target: Callable[..., object]) -> str:
    return getattr(target, '__qualname__', repr(target))


def _checkpoint_run(run: Run, invariants: Sequence[Invariant]) -> None:
    for invariant in invariants:
        invariant(run)

    run.log(f'checkpoint held {len(invariants)} invariants')


def simulate(
    *,
    actions: Sequence[Action],
    checkpoint_every: int,
    invariants: Sequence[Invariant],
    seed: int,
    setup: Callable[[Run], None] | None = None,
    step_count: int,
) -> Run:
    if not actions:
        message = 'simulate needs at least one action'
        raise SimulationBoundsError(message)

    _bounds_validate('seed', seed, value_min=0, value_max=SEED_MAX)
    _bounds_validate('step_count', step_count, value_min=1, value_max=STEP_COUNT_MAX)
    _bounds_validate('checkpoint_every', checkpoint_every, value_min=1, value_max=step_count)

    rng = random.Random(seed)
    run = Run(rng=rng, seed=seed)

    if setup is not None:
        setup(run)

    for step in range(step_count):
        run.step = step
        action = rng.choice(actions)

        try:
            run.log(f'action {_callable_name(action)}')
            action(run)

            if (step + 1) % checkpoint_every == 0:
                _checkpoint_run(run, invariants)
        except Exception as error:
            raise SimulationFailureError(
                cause=error,
                journal_tail=run.journal_tail(),
                seed=seed,
                step=step,
            ) from error

    return run
