from __future__ import annotations

import builtins
import sys
import threading

from typing import TYPE_CHECKING

from kaleidoscope.constants import MEMORY_DIFF_ROWS_MAX, StateKey
from kaleidoscope.panel import Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext

try:
    from pympler import muppy, summary as pympler_summary
    HAS_PYMPLER = True
except ImportError:
    HAS_PYMPLER = False

_STDLIB_MODULES: frozenset[str] = getattr(sys, 'stdlib_module_names', frozenset())

_BUILTINS: frozenset[str] = frozenset(
    name for name, obj in vars(builtins).items()
    if isinstance(obj, type)
)

_BUILTIN_PREFIXES = ('builtins.', 'builtin.')


def _categorize(type_name: str) -> str:  # noqa: PLR0911
    if type_name.startswith(_BUILTIN_PREFIXES):
        return 'builtin'

    bare = type_name.split('(', maxsplit=1)[0].strip()

    if '.' not in bare:
        if bare in _BUILTINS:
            return 'builtin'

        return 'stdlib'

    module = bare.split('.')[0]

    if module.startswith('_'):
        return 'stdlib'

    if module in _STDLIB_MODULES:
        return 'stdlib'

    if module == 'django':
        return 'django'

    return 'project'


class MemoryPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'memory'
    title = 'Memory'
    default_enabled = False
    isolate = True

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}
        self._lock = threading.Lock()

    def _format_size(self, size: int) -> str:
        if abs(size) < 1024:
            return f'{size} B'

        if abs(size) < 1024 * 1024:
            return f'{size / 1024:.1f} KB'

        return f'{size / 1024 / 1024:.2f} MB'

    def get_data(self) -> dict:
        with self._lock:
            data = dict(self._data)

        if not HAS_PYMPLER:
            data['error'] = 'pympler is not installed. Run: pip install pympler'

        return data

    def get_summary(self) -> str:
        with self._lock:
            return self._data.get('total_size_display', '')  # ty:ignore[invalid-return-type]

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request

        if not HAS_PYMPLER:
            return

        if context.is_ajax:
            return

        context.state[StateKey.MEMORY_BEFORE] = pympler_summary.summarize(
            muppy.get_objects(),
        )

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        _ = request
        _ = response

        if not HAS_PYMPLER:
            return

        before = context.state.get(StateKey.MEMORY_BEFORE)

        if not before:
            return

        after = pympler_summary.summarize(muppy.get_objects())
        diff = pympler_summary.get_diff(before, after)
        diff.sort(key=lambda row: abs(row[2]), reverse=True)

        total_size = sum(row[2] for row in after)
        total_objects = sum(row[1] for row in after)

        rows = []

        for row in diff[:MEMORY_DIFF_ROWS_MAX]:
            type_name = str(row[0])

            rows.append({
                'category': _categorize(type_name),
                'count': row[1],
                'size': row[2],
                'size_display': self._format_size(row[2]),
                'type': type_name,
            })

        with self._lock:
            self._data = {
                'diff': rows,
                'total_objects': total_objects,
                'total_size': total_size,
                'total_size_display': self._format_size(total_size),
            }
