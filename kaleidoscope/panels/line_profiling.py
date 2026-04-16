from __future__ import annotations

import linecache
import threading

from typing import TYPE_CHECKING

from kaleidoscope.constants import (
    LINE_PROFILER_FUNCTIONS_MAX,
    LINE_PROFILER_TIMINGS_MAX,
    WRAPPED_DEPTH_MAX,
    StateKey,
)
from kaleidoscope.normalizer import PathShortener
from kaleidoscope.panel import Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext


try:
    from line_profiler import LineProfiler
    HAS_LINE_PROFILER = True
except ImportError:
    HAS_LINE_PROFILER = False

_path_shortener = PathShortener(max_length=80, tail_segments=3)


class LineProfilingPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'line_profiling'
    title = 'Line Profiler'
    default_enabled = False
    isolate = True

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}
        self._lock = threading.Lock()

    def _build_results(self, stats: object) -> list[dict]:
        timings = getattr(stats, 'timings', {})
        unit = getattr(stats, 'unit', 1e-6)

        results = []

        for func_key, line_timings in list(timings.items())[:LINE_PROFILER_FUNCTIONS_MAX]:
            if not line_timings:
                continue

            filename, start_lineno, func_name = func_key
            total_time = sum(
                t[2] for t in line_timings[:LINE_PROFILER_TIMINGS_MAX]
            ) * unit * 1000

            lines = []

            for lineno, nhits, time_val in line_timings[:LINE_PROFILER_TIMINGS_MAX]:
                time_ms = time_val * unit * 1000
                pct = (time_ms / total_time * 100) if total_time > 0 else 0
                per_hit = time_ms / nhits if nhits > 0 else 0
                source = linecache.getline(filename, lineno).rstrip()

                lines.append({
                    'hits': nhits,
                    'lineno': lineno,
                    'pct': round(pct, 1),
                    'per_hit_ms': round(per_hit, 4),
                    'source': source,
                    'time_ms': round(time_ms, 4),
                })

            results.append({
                'filename': _path_shortener.shorten(filename),
                'full_path': filename,
                'func_name': func_name,
                'lines': lines,
                'start_lineno': start_lineno,
                'total_time_ms': round(total_time, 2),
            })

        results.sort(key=lambda r: r['total_time_ms'], reverse=True)

        return results

    def _resolve_functions(self, request: HttpRequest) -> list:
        from django.urls import Resolver404, resolve  # noqa: PLC0415

        try:
            match = resolve(request.path_info)
        except Resolver404:
            return []

        funcs = []
        view_func = match.func

        if hasattr(view_func, 'view_class'):
            cls = view_func.view_class
            method_name = request.method.lower()

            if hasattr(cls, method_name):
                funcs.append(getattr(cls, method_name))

            if hasattr(cls, 'dispatch'):
                funcs.append(cls.dispatch)
        else:
            func = view_func

            for _ in range(WRAPPED_DEPTH_MAX):
                if not hasattr(func, '__wrapped__'):
                    break

                funcs.append(func)
                func = func.__wrapped__

            funcs.append(func)

        return funcs[:LINE_PROFILER_FUNCTIONS_MAX]

    def get_data(self) -> dict:
        with self._lock:
            data = dict(self._data)

        if not HAS_LINE_PROFILER:
            data['error'] = (
                'line_profiler is not installed. '
                'Run: pip install line-profiler'
            )

        return data

    def get_summary(self) -> str:
        with self._lock:
            duration = self._data.get('duration_ms', 0)
            count = self._data.get('function_count', 0)

        if duration:
            return f'{count} functions, {duration:.0f} ms'

        return ''

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        if not HAS_LINE_PROFILER:
            return

        if context.is_ajax:
            return

        funcs = self._resolve_functions(request)

        if not funcs:
            return

        profiler = LineProfiler()

        for func in funcs:
            profiler.add_function(func)

        profiler.enable_by_count()
        context.state[StateKey.LINE_PROFILER] = profiler

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        _ = request
        _ = response

        profiler = context.state.get(StateKey.LINE_PROFILER)

        if not profiler:
            return

        profiler.disable_by_count()
        stats = profiler.get_stats()
        results = self._build_results(stats)

        duration = sum(r['total_time_ms'] for r in results)

        with self._lock:
            self._data = {
                'duration_ms': round(duration, 2),
                'function_count': len(results),
                'functions': results,
                'has_data': bool(results),
            }
