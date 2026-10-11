from __future__ import annotations

import re

from typing import TYPE_CHECKING

from tests.simulation.exceptions import SimulationInvariantError
from tests.testapp.work import fragments_render, response_content
from tests.toolbar import shell_text

if TYPE_CHECKING:
    from tests.testapp.work import CacheOperation, WorkPlan


BODY_CLOSE = re.compile(r'</body\s*>', re.IGNORECASE)
INJECTABLE_KINDS = frozenset({'html', 'html_upper', 'latin1', 'xhtml'})
INJECTABLE_STATUSES = frozenset(range(200, 300)) - {204, 205, 206}

SERVER_TIMING_ENTRY = re.compile(
    r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+;dur=-?\d+(?:\.\d+)?;desc=\"(?:[^\"\\\x00-\x1f\x7f]|\\.)*\"",
)

STATIC_REFERENCE = re.compile(r'/static/([^"\'?#) \n\r>]+)')


def body_expected(plan: WorkPlan, body_length: int) -> bytes:
    fragments = fragments_render(plan)

    return response_content(plan, fragments, body_length)


def body_injected(body: bytes, charset: str) -> bytes:
    text = body.decode(charset)
    closings = list(BODY_CLOSE.finditer(text))

    check(bool(closings), 'an injectable body must close its body element')

    index = closings[-1].start()
    injected = text[:index] + shell_text() + text[index:]

    return injected.encode(charset)


def cache_call_expected(operation: CacheOperation, present: set[str]) -> tuple[str, bool]:
    key = operation.keys[0] if operation.keys else ''

    if operation.name in {'get', 'getd'}:
        return 'GET', key in present

    if operation.name == 'has':
        return 'HAS_KEY', key in present

    if operation.name == 'gos':
        hit = key in present

        present.add(key)

        return 'GET_OR_SET', hit

    if operation.name == 'many':
        return 'GET_MANY', set(operation.keys) <= present

    if operation.name in {'add', 'set'}:
        present.add(key)

        return operation.name.upper(), False

    if operation.name == 'incr':
        return 'INCR', False

    if operation.name == 'del':
        present.discard(key)

        return 'DELETE', False

    present.clear()

    return 'CLEAR', False


def cache_calls_expected(plan: WorkPlan, present: set[str]) -> list[tuple[str, bool]]:
    return [cache_call_expected(operation, present) for operation in plan.cache_operations]


def charset_of(plan: WorkPlan) -> str:
    if plan.kind == 'latin1':
        return 'iso-8859-1'

    return 'utf-8'


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SimulationInvariantError(message)


def injection_expected(plan: WorkPlan, *, is_ajax: bool) -> bool:
    if is_ajax:
        return False

    if plan.fail:
        return False

    if plan.status not in INJECTABLE_STATUSES:
        return False

    return plan.kind in INJECTABLE_KINDS


def server_timing_entries(header: str) -> list[str]:
    entries = [match.group(0) for match in SERVER_TIMING_ENTRY.finditer(header)]

    check(', '.join(entries) == header, f'Server-Timing is malformed: {header!r}')

    return entries


def static_used_expected(content: bytes, charset: str) -> list[str]:
    try:
        text = content.decode(charset, errors='replace')
    except (LookupError, UnicodeError):
        text = content.decode('utf-8', errors='replace')

    return sorted(set(STATIC_REFERENCE.findall(text)))
