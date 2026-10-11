from __future__ import annotations

import random

import pytest

from typing import TYPE_CHECKING

from tests.simulation.engine import SOMETIMES_TARGETS, SOMETIMES_TARGETS_ASGI, ToolbarSimulation
from tests.simulation.fault import Faults
from tests.simulation.pytest_plugin import step_count_from_environment
from tests.simulation.run import simulate
from tests.testapp.work import KINDS

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from tests.simulation.run import Run


pytestmark = [pytest.mark.simulation, pytest.mark.django_db]
CHECKPOINT_EVERY = 25
FAULTS = Faults(cache_rate=0.04, database_rate=0.03, panel_rate=0.03)
STEP_COUNT = step_count_from_environment()
SWEEP_SEEDS = 12
SWEEP_STEP_COUNT = 400


def _simulated(
    simulation: ToolbarSimulation,
    *,
    seed: int,
    actions: Sequence[Callable[[Run], None]] | None = None,
    checked: bool = True,
    step_count: int = STEP_COUNT,
) -> Run:
    invariants = simulation.invariants() if checked else ()

    with simulation.installed():
        return simulate(
            actions=actions or simulation.actions(),
            checkpoint_every=CHECKPOINT_EVERY,
            invariants=invariants,
            seed=seed,
            setup=simulation.setup,
            step_count=step_count,
        )


def test_simulation_holds_every_invariant(simulation_seed: int) -> None:
    simulation = ToolbarSimulation()

    _simulated(simulation, seed=simulation_seed)


def test_simulation_holds_every_invariant_under_asgi(simulation_seed: int) -> None:
    simulation = ToolbarSimulation(asgi=True)

    _simulated(simulation, seed=simulation_seed)


def test_simulation_holds_every_invariant_swarmed(simulation_seed: int) -> None:
    rng = random.Random(simulation_seed)
    simulation, actions = ToolbarSimulation.swarm(rng)

    _simulated(simulation, seed=simulation_seed, actions=actions)


def test_simulation_holds_every_invariant_under_faults(simulation_seed: int) -> None:
    simulation = ToolbarSimulation(faults=FAULTS)

    _simulated(simulation, seed=simulation_seed)


def test_simulation_holds_every_invariant_under_faults_and_asgi(simulation_seed: int) -> None:
    simulation = ToolbarSimulation(asgi=True, faults=FAULTS)

    _simulated(simulation, seed=simulation_seed)


def test_simulation_reaches_every_sometimes_target() -> None:
    reached: dict[str, int] = {}

    for seed in range(SWEEP_SEEDS):
        simulation = ToolbarSimulation(asgi=seed % 2 == 1)
        run = _simulated(simulation, seed=seed, checked=False, step_count=SWEEP_STEP_COUNT)

        for name, count in run.sometimes_counts.items():
            reached[name] = reached.get(name, 0) + count

    targets = (*SOMETIMES_TARGETS, *SOMETIMES_TARGETS_ASGI, *(f'kind {kind}' for kind in KINDS))
    unreached = sorted(target for target in targets if reached.get(target, 0) == 0)

    assert unreached == []
