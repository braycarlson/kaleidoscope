from __future__ import annotations

import functools
import math

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from unittest import mock

from django.db import connection

from kaleidoscope.panels.cache import CachePanel
from kaleidoscope.panels.queries import QueriesPanel
from kaleidoscope.panels.request import RequestPanel
from kaleidoscope.panels.signals import SignalsPanel
from kaleidoscope.panels.static_files import StaticFilesPanel
from kaleidoscope.panels.templates import TemplatesPanel
from kaleidoscope.panels.timer import TimerPanel
from kaleidoscope.panels.versions import VersionsPanel

from tests.simulation.exceptions import (
    SimulationBoundsError,
    SimulationDatabaseFaultError,
    SimulationFaultError,
)
from tests.testapp import cache as cache_backend

if TYPE_CHECKING:
    import random

    from collections.abc import Callable, Iterator


FAULT_RATE_MAX = 1.0
FAULTS_FIRED_MAX = 10_000

PANEL_HOOKS_AFTER = (
    (CachePanel, 'process_request'),
    (CachePanel, 'process_response'),
    (QueriesPanel, 'process_request'),
    (QueriesPanel, 'process_response'),
    (RequestPanel, 'process_request'),
    (RequestPanel, 'process_response'),
    (SignalsPanel, 'process_request'),
    (SignalsPanel, 'process_response'),
    (StaticFilesPanel, 'process_response'),
    (TemplatesPanel, 'process_request'),
    (TemplatesPanel, 'process_response'),
    (TimerPanel, 'process_response'),
)

PANEL_HOOKS_BEFORE = (
    (CachePanel, 'get_summary'),
    (CachePanel, 'process_request'),
    (QueriesPanel, 'get_server_timing'),
    (QueriesPanel, 'process_request'),
    (RequestPanel, 'get_summary'),
    (RequestPanel, 'process_request'),
    (SignalsPanel, 'get_data'),
    (SignalsPanel, 'process_request'),
    (TemplatesPanel, 'process_request'),
    (TimerPanel, 'get_server_timing'),
    (VersionsPanel, 'get_data'),
)


@dataclass(frozen=True)
class Faults:
    cache_rate: float = 0.0
    database_rate: float = 0.0
    panel_rate: float = 0.0

    def __post_init__(self) -> None:
        _rate_validate('cache_rate', self.cache_rate)
        _rate_validate('database_rate', self.database_rate)
        _rate_validate('panel_rate', self.panel_rate)

        rates = (self.cache_rate, self.database_rate, self.panel_rate)

        if not any(rates):
            message = 'faults need at least one rate above zero'
            raise SimulationBoundsError(message)


@dataclass
class FaultLedger:
    fired: list[tuple[str, str, str]] = field(default_factory=list)
    statements_passed: int = 0

    def any_fired(self, category: str) -> bool:
        return any(entry[0] == category for entry in self.fired)

    def panel_fired(self, panel_id: str, method: str, *, position: str | None = None) -> bool:
        for category, target, where in self.fired:
            if category != 'panel':
                continue

            if target != f'{panel_id}.{method}':
                continue

            if position is None:
                return True

            if where == position:
                return True

        return False

    def record(self, category: str, target: str, where: str) -> None:
        if len(self.fired) >= FAULTS_FIRED_MAX:
            message = f'faults fired exceed {FAULTS_FIRED_MAX} in one step'
            raise SimulationBoundsError(message)

        entry = (category, target, where)

        self.fired.append(entry)

    def reset(self) -> None:
        self.fired.clear()
        self.statements_passed = 0


def _hook_faulting(
    original: Callable,
    *,
    ledger: FaultLedger,
    panel_id: str,
    position: str,
    rate: float,
    rng: random.Random,
) -> Callable:
    target = f'{panel_id}.{original.__name__}'

    @functools.wraps(original)
    def wrapper(*arguments: Any, **keywords: Any) -> Any:
        if position == 'before':
            if rng.random() < rate:
                ledger.record('panel', target, 'before')

                message = f'simulated fault before {target}'
                raise SimulationFaultError(message)

        result = original(*arguments, **keywords)

        if position == 'after':
            if rng.random() < rate:
                ledger.record('panel', target, 'after')

                message = f'simulated fault after {target}'
                raise SimulationFaultError(message)

        return result

    return wrapper


def _rate_validate(name: str, rate: float) -> None:
    if math.isnan(rate):
        message = f'{name} must be within 0.0..{FAULT_RATE_MAX}: {rate}'
        raise SimulationBoundsError(message)

    if rate < 0.0:
        message = f'{name} must be within 0.0..{FAULT_RATE_MAX}: {rate}'
        raise SimulationBoundsError(message)

    if rate > FAULT_RATE_MAX:
        message = f'{name} must be within 0.0..{FAULT_RATE_MAX}: {rate}'
        raise SimulationBoundsError(message)


@contextmanager
def faults_installed(
    faults: Faults | None,
    rng: random.Random,
    ledger: FaultLedger,
) -> Iterator[None]:
    if faults is None:
        yield

        return

    def statement(execute: Callable, sql: str, params: object, many: bool, context: dict) -> object:
        if faults.database_rate:
            if rng.random() < faults.database_rate:
                ledger.record('database', sql[:40], 'statement')

                message = 'simulated database fault'
                raise SimulationDatabaseFaultError(message)

        ledger.statements_passed += 1

        return execute(sql, params, many, context)

    def cache_operation(operation: str) -> None:
        if faults.cache_rate:
            if rng.random() < faults.cache_rate:
                ledger.record('cache', operation, 'operation')

                message = f'simulated cache fault on {operation}'
                raise SimulationFaultError(message)

    with ExitStack() as stack:
        stack.enter_context(connection.execute_wrapper(statement))
        stack.enter_context(mock.patch.object(cache_backend, 'fault_hook', cache_operation))

        if faults.panel_rate:
            _panel_hooks_patched(stack, faults=faults, ledger=ledger, rng=rng)

        yield


def _panel_hooks_patched(
    stack: ExitStack,
    *,
    faults: Faults,
    ledger: FaultLedger,
    rng: random.Random,
) -> None:
    positions_by_hook: dict[tuple[type, str], list[str]] = {}

    for hook in PANEL_HOOKS_BEFORE:
        positions_by_hook.setdefault(hook, []).append('before')

    for hook in PANEL_HOOKS_AFTER:
        positions_by_hook.setdefault(hook, []).append('after')

    for (owner, name), positions in positions_by_hook.items():
        wrapped = getattr(owner, name)

        for position in positions:
            wrapped = _hook_faulting(
                wrapped,
                ledger=ledger,
                panel_id=owner.panel_id,
                position=position,
                rate=faults.panel_rate,
                rng=rng,
            )

        stack.enter_context(mock.patch.object(owner, name, wrapped))
