from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from tests.simulation.exceptions import SimulationBoundsError

if TYPE_CHECKING:
    import random

    from collections.abc import Sequence


KEEP_CHANCE_DEFAULT = 0.5
KEEP_CHANCE_MAX = 1.0
Item = TypeVar('Item')


def swarmed(
    items: Sequence[Item],
    rng: random.Random,
    *,
    keep_chance: float = KEEP_CHANCE_DEFAULT,
) -> tuple[Item, ...]:
    if not items:
        message = 'swarm needs at least one item'
        raise SimulationBoundsError(message)

    if keep_chance <= 0.0:
        message = f'keep_chance must be within (0.0, {KEEP_CHANCE_MAX}]: {keep_chance}'
        raise SimulationBoundsError(message)

    if keep_chance > KEEP_CHANCE_MAX:
        message = f'keep_chance must be within (0.0, {KEEP_CHANCE_MAX}]: {keep_chance}'
        raise SimulationBoundsError(message)

    distinct = list(dict.fromkeys(items))
    kept = [item for item in distinct if rng.random() < keep_chance]

    if not kept:
        kept = [rng.choice(distinct)]

    return tuple(item for item in items if item in kept)
