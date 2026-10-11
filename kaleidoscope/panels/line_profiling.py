from __future__ import annotations

import inspect
import linecache

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from django.http import HttpRequest
from django.urls import Resolver404, resolve
from line_profiler import LineProfiler

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpResponse


LINE_PROFILER_FUNCTIONS_MAX = 32
LINE_PROFILER_TIMINGS_MAX = 10_000
PATH_LENGTH_MAX = 80
PATH_TAIL_SEGMENTS = 3


def _function_result(filename: str, line_start: int, name: str, timings: list, unit: float) -> dict:
    if not isinstance(timings, list):
        message = f'timings must be a list, not {type(timings).__name__}'
        raise TypeError(message)

    if unit <= 0:
        message = f'unit must be positive: {unit}'
        raise ValueError(message)

    time_ms_total = sum(time for _, _, time in timings) * unit * 1000
    lines = []

    for line_number, hits, time in timings:
        time_ms = time * unit * 1000
        share = (time_ms / time_ms_total * 100) if time_ms_total > 0 else 0
        per_hit_ms = time_ms / hits if hits > 0 else 0

        line = {
            'hits': hits,
            'lineno': line_number,
            'pct': round(share, 1),
            'per_hit_ms': round(per_hit_ms, 4),
            'source': linecache.getline(filename, line_number).rstrip(),
            'time_ms': round(time_ms, 4),
        }

        lines.append(line)

    return {
        'filename': _path_shortened(filename),
        'full_path': filename,
        'func_name': name,
        'lines': lines,
        'start_lineno': line_start,
        'total_time_ms': round(time_ms_total, 2),
    }


def _functions_resolved(request: HttpRequest) -> list:
    if not isinstance(request, HttpRequest):
        message = f'the line profiler resolves an HttpRequest, not {type(request).__name__}'
        raise TypeError(message)

    try:
        match = resolve(request.path_info)
    except Resolver404:
        return []

    functions = []
    view = match.func

    if hasattr(view, 'view_class'):
        cls = view.view_class
        method_name = (request.method or 'get').lower()

        if hasattr(cls, method_name):
            functions.append(getattr(cls, method_name))

        if hasattr(cls, 'dispatch'):
            functions.append(cls.dispatch)
    else:
        functions.append(inspect.unwrap(view))

    return functions


def _path_shortened(path: str) -> str:
    if not isinstance(path, str):
        message = f'path must be text: {path!r}'
        raise TypeError(message)

    normalized = path.replace('\\', '/')

    if len(normalized) <= PATH_LENGTH_MAX:
        return normalized

    parts = PurePosixPath(normalized).parts

    if len(parts) <= PATH_TAIL_SEGMENTS:
        return normalized

    short = '.../' + '/'.join(parts[-PATH_TAIL_SEGMENTS:])

    if len(short) > PATH_LENGTH_MAX:
        return short[:PATH_LENGTH_MAX - 3] + '...'

    return short


def _results_build(stats: object) -> list[dict]:
    timings = getattr(stats, 'timings', {})
    unit = getattr(stats, 'unit', 1e-6)

    if not isinstance(timings, dict):
        message = f'the line profiler reported its timings as a {type(timings).__name__}'
        raise TypeError(message)

    if unit <= 0:
        message = f'the line profiler reported a unit that is not positive: {unit}'
        raise ValueError(message)

    results = []

    for key, line_timings in list(timings.items())[:LINE_PROFILER_FUNCTIONS_MAX]:
        if not line_timings:
            continue

        filename, line_start, name = key
        result = _function_result(
            filename,
            line_start,
            name,
            line_timings[:LINE_PROFILER_TIMINGS_MAX],
            unit,
        )

        results.append(result)

    results.sort(key=_total_time_ms, reverse=True)

    return results


def _total_time_ms(result: dict) -> float:
    return result['total_time_ms']


class LineProfilingPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'line_profiling'
    title = 'Line Profiler'
    default_enabled = False
    follows_view = True
    isolate = True

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}

    def get_data(self) -> dict:
        return dict(self._data)

    def get_summary(self) -> str:
        data = self._data
        duration_ms = data.get('duration_ms', 0)

        if duration_ms:
            return f'{data.get("function_count", 0)} functions, {duration_ms:.0f} ms'

        return ''

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        if context.is_ajax:
            return

        functions = _functions_resolved(request)

        if not functions:
            return

        profiler = LineProfiler()

        for function in functions:
            profiler.add_function(function)

        profiler.enable_by_count()

        context.state[self.panel_id] = profiler

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

        profiler = context.state.get(self.panel_id)

        if profiler is None:
            return

        profiler.disable_by_count()

        results = _results_build(profiler.get_stats())
        duration_ms_outermost = max((result['total_time_ms'] for result in results), default=0.0)

        self._data = {
            'duration_ms': duration_ms_outermost,
            'function_count': len(results),
            'functions': results,
            'has_data': bool(results),
        }
