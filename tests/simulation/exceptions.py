from __future__ import annotations

from django.db import OperationalError


class SimulationError(Exception):
    """The base exception class for all simulation exceptions."""


class SimulationBoundsError(SimulationError):
    """An exception that is raised when a run is configured outside the harness limits."""


class SimulationDatabaseFaultError(OperationalError, SimulationError):
    """An exception that is raised when the simulation faults a database statement."""


class SimulationFailureError(SimulationError):
    """An exception that is raised when a run fails, carrying the seed, step, cause, and journal."""

    def __init__(
        self,
        *,
        cause: BaseException,
        journal_tail: list[str],
        seed: int,
        step: int,
    ) -> None:
        self.cause = cause
        self.seed = seed
        self.step = step
        tail = '\n'.join(journal_tail)

        super().__init__(f'seed={seed} step={step}: {cause!r}\n{tail}')


class SimulationFaultError(SimulationError):
    """An exception that is raised when the simulation injects a fault into the code under test."""


class SimulationInvariantError(SimulationError):
    """An exception that is raised when an invariant does not hold at a checkpoint or probe."""
