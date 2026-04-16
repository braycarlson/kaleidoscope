from __future__ import annotations

import functools
import threading
import time

from contextvars import ContextVar
from typing import TYPE_CHECKING

from kaleidoscope.constants import CACHE_CALLS_MAX, CACHES_MAX, FORMAT_ARGS_MAX_LENGTH
from kaleidoscope.panel import Installable, Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from typing import Any, Callable

    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext


TRACKED_METHODS = (
    'add',
    'clear',
    'delete',
    'delete_many',
    'get',
    'get_many',
    'get_or_set',
    'has_key',
    'incr',
    'set',
    'set_many',
)

_collecting: ContextVar[list | None] = ContextVar('_cache_collecting', default=None)

_READ_METHODS = ('GET', 'GET_OR_SET', 'HAS_KEY')

_patch_lock = threading.Lock()


def _format_args(args: tuple, kwargs: dict) -> str:
    parts = [repr(arg) for arg in args]
    parts.extend(f'{key}={value!r}' for key, value in kwargs.items())
    result = ', '.join(parts)

    if len(result) > FORMAT_ARGS_MAX_LENGTH:
        result = result[:FORMAT_ARGS_MAX_LENGTH] + '...'

    return result


def _ensure_patched(cache: object, alias: str) -> None:
    if getattr(cache, '_kaleidoscope_patched', False):
        return

    with _patch_lock:
        if getattr(cache, '_kaleidoscope_patched', False):
            return

        for method_name in TRACKED_METHODS:
            original = getattr(cache, method_name, None)

            if not original:
                continue

            @functools.wraps(original)
            def wrapper(
                *args: Any,
                _orig: Callable = original,
                _method: str = method_name,
                _alias: str = alias,
                **kwargs: Any,
            ) -> Any:
                calls = _collecting.get(None)

                if calls is None:
                    return _orig(*args, **kwargs)

                method_upper = _method.upper()
                start = time.perf_counter_ns()

                try:
                    result = _orig(*args, **kwargs)
                except Exception:
                    duration = (time.perf_counter_ns() - start) / 1_000_000

                    if len(calls) < CACHE_CALLS_MAX:
                        calls.append({
                            'alias': _alias,
                            'args': _format_args(args, kwargs),
                            'duration_ms': round(duration, 2),
                            'hit': False,
                            'method': method_upper,
                        })

                    raise

                duration = (time.perf_counter_ns() - start) / 1_000_000
                hit = result is not None if method_upper in _READ_METHODS else False

                if len(calls) < CACHE_CALLS_MAX:
                    calls.append({
                        'alias': _alias,
                        'args': _format_args(args, kwargs),
                        'duration_ms': round(duration, 2),
                        'hit': hit,
                        'method': method_upper,
                    })

                return result

            setattr(cache, method_name, wrapper)

        cache._kaleidoscope_patched = True


def _patch_all_caches() -> None:
    from django.core.cache import caches  # noqa: PLC0415

    aliases = list(caches)[:CACHES_MAX]

    for alias in aliases:
        cache = caches[alias]
        _ensure_patched(cache, alias)


class CachePanel(Panel, Installable, RequestHook, ResponseHook):
    panel_id = 'cache'
    title = 'Cache'

    def __init__(self) -> None:
        super().__init__()

        self._data: list[dict] = []
        self._lock = threading.Lock()

    def install(self) -> None:
        _patch_all_caches()

    def uninstall(self) -> None:
        pass

    def get_data(self) -> dict:
        with self._lock:
            calls = list(self._data)

        hits = sum(1 for c in calls if c.get('hit'))
        misses = sum(
            1 for c in calls
            if c.get('method') in _READ_METHODS and not c.get('hit')
        )
        total_time = sum(c.get('duration_ms', 0) for c in calls)

        return {
            'calls': calls,
            'count': len(calls),
            'hits': hits,
            'misses': misses,
            'total_time': round(total_time, 2),
        }

    def get_summary(self) -> str:
        with self._lock:
            count = len(self._data)
            hits = sum(1 for c in self._data if c.get('hit'))
            misses = sum(
                1 for c in self._data
                if c.get('method') in _READ_METHODS and not c.get('hit')
            )

        if not count:
            return '0 calls'

        parts = [f'{count} calls']

        if hits or misses:
            parts.append(f'{hits} hits, {misses} misses')

        return ', '.join(parts)

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request
        _ = context

        _patch_all_caches()
        _collecting.set([])

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        _ = request
        _ = response

        calls = _collecting.get(None) or []
        _collecting.set(None)

        with self._lock:
            if context.is_ajax:
                self._data.extend(calls)
            else:
                self._data = calls
