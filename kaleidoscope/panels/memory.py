from __future__ import annotations

import builtins
import sys

from enum import StrEnum
from typing import TYPE_CHECKING

from pympler import muppy
from pympler import summary as pympler_summary

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


MEMORY_DIFF_ROWS_MAX = 50
_BUILTIN_PREFIXES = ('builtins.', 'builtin.')
_INTEGER_CACHED_MAX = 256
_INTEGER_CACHED_MIN = -5
_BUILTINS = frozenset(name for name, value in vars(builtins).items() if isinstance(value, type))
_STDLIB_MODULES: frozenset[str] = getattr(sys, 'stdlib_module_names', frozenset())
_SUMMARY_ROW_LENGTH = 3


class Category(StrEnum):
    BUILTIN = 'builtin'
    DJANGO = 'django'
    PROJECT = 'project'
    STDLIB = 'stdlib'


def _category_of(type_name: str) -> Category:
    if not isinstance(type_name, str):
        message = f'type_name must be text: {type_name!r}'
        raise TypeError(message)

    if type_name.startswith(_BUILTIN_PREFIXES):
        return Category.BUILTIN

    bare = type_name.split('(', maxsplit=1)[0].strip()

    if '.' not in bare:
        if bare in _BUILTINS:
            return Category.BUILTIN

        return Category.STDLIB

    module = bare.split('.')[0]

    if module.startswith('_'):
        return Category.STDLIB

    if module in _STDLIB_MODULES:
        return Category.STDLIB

    if module == 'django':
        return Category.DJANGO

    return Category.PROJECT


def _diff_rows(before: list, after: list, footprint: list) -> list:
    if not isinstance(before, list):
        message = f'before must be a summary list, not {type(before).__name__}'
        raise TypeError(message)

    if not isinstance(after, list):
        message = f'after must be a summary list, not {type(after).__name__}'
        raise TypeError(message)

    if not isinstance(footprint, list):
        message = f'footprint must be a summary list, not {type(footprint).__name__}'
        raise TypeError(message)

    diff = pympler_summary.get_diff(before, after)
    corrected = pympler_summary.get_diff(footprint, diff)

    return [row for row in corrected if any(row[1:])]


def _is_integer_cached(value: object) -> bool:
    if not isinstance(value, int):
        return False

    if value < _INTEGER_CACHED_MIN:
        return False

    return value <= _INTEGER_CACHED_MAX


def _size_absolute(row: list) -> int:
    return abs(row[2])


def _size_text(size: int) -> str:
    if isinstance(size, bool):
        message = f'size must be an integer, not a bool: {size!r}'
        raise TypeError(message)

    if not isinstance(size, int):
        message = f'size must be an integer: {size!r}'
        raise TypeError(message)

    if abs(size) < 1024:
        return f'{size} B'

    if abs(size) < 1024 * 1024:
        return f'{size / 1024:.1f} KB'

    return f'{size / 1024 / 1024:.2f} MB'


def _summarized() -> list:
    summary = pympler_summary.summarize(muppy.get_objects())

    if not isinstance(summary, list):
        message = f'pympler summarized the heap as a {type(summary).__name__}, not a list'
        raise TypeError(message)

    return summary


def _summary_footprint(summary: list) -> list:
    if not isinstance(summary, list):
        message = f'summary must be a list, not {type(summary).__name__}'
        raise TypeError(message)

    owned = {id(summary): summary}

    for row in summary:
        if len(row) != _SUMMARY_ROW_LENGTH:
            message = f'a summary row holds a type, a count, and a size, not {row!r}'
            raise ValueError(message)

        owned[id(row)] = row
        owned[id(row[0])] = row[0]

        for value in row[1:]:
            if not _is_integer_cached(value):
                owned[id(value)] = value

    return pympler_summary.summarize(list(owned.values()))


class MemoryPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'memory'
    title = 'Memory'
    default_enabled = False
    isolate = True

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}

    def get_data(self) -> dict:
        return dict(self._data)

    def get_summary(self) -> str:
        return self._data.get('total_size_display', '')

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request

        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        if context.is_ajax:
            return

        context.state[self.panel_id] = _summarized()

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        _ = request
        _ = response

        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        before = context.state.get(self.panel_id)

        if before is None:
            return

        after = _summarized()
        footprint = _summary_footprint(before)
        diff = _diff_rows(before, after, footprint)

        diff.sort(key=_size_absolute, reverse=True)

        rows = [
            {
                'category': _category_of(str(row[0])),
                'count': row[1],
                'size': row[2],
                'size_display': _size_text(row[2]),
                'type': str(row[0]),
            }
            for row in diff[:MEMORY_DIFF_ROWS_MAX]
        ]

        objects_total = sum(row[1] for row in after) - sum(row[1] for row in footprint)
        size_total = sum(row[2] for row in after) - sum(row[2] for row in footprint)

        if objects_total < 0:
            message = f'the heap holds {objects_total} objects once its snapshot is left out'
            raise RuntimeError(message)

        if size_total < 0:
            message = f'the heap holds {size_total} bytes once its snapshot is left out'
            raise RuntimeError(message)

        self._data = {
            'diff': rows,
            'total_objects': objects_total,
            'total_size': size_total,
            'total_size_display': _size_text(size_total),
        }
