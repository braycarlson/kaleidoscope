from __future__ import annotations

import functools
import logging
import reprlib
import threading
import time
import weakref

from contextvars import ContextVar
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

from django.core.cache import caches

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Installable, Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from typing import Any, Callable

    from django.http import HttpRequest, HttpResponse


CACHE_CALLS_MAX = 50_000
CACHES_MAX = 256
FORMAT_ARGS_LENGTH_MAX = 200
_ARGUMENT_ITEMS_MAX = 20
_active: ContextVar[list | None] = ContextVar('_cache_active', default=None)
_collecting: ContextVar[list | None] = ContextVar('_cache_collecting', default=None)
_patch_lock = threading.Lock()

logger = logging.getLogger(__name__)


class CacheMethod(StrEnum):
    ADD = 'add'
    CLEAR = 'clear'
    DELETE = 'delete'
    DELETE_MANY = 'delete_many'
    GET = 'get'
    GET_MANY = 'get_many'
    GET_OR_SET = 'get_or_set'
    HAS_KEY = 'has_key'
    INCR = 'incr'
    SET = 'set'
    SET_MANY = 'set_many'


class HitsMisses(NamedTuple):
    hits: int
    misses: int


_NESTED_WRITES = frozenset({CacheMethod.ADD, CacheMethod.SET})

_READ_METHODS = frozenset({
    CacheMethod.GET,
    CacheMethod.GET_MANY,
    CacheMethod.GET_OR_SET,
    CacheMethod.HAS_KEY,
})

_READ_METHOD_NAMES = frozenset(method.upper() for method in _READ_METHODS)


@functools.cache
def _arguments_reprlib() -> reprlib.Repr:
    instance = reprlib.Repr()
    instance.maxdict = _ARGUMENT_ITEMS_MAX
    instance.maxfrozenset = _ARGUMENT_ITEMS_MAX
    instance.maxlist = _ARGUMENT_ITEMS_MAX
    instance.maxlong = FORMAT_ARGS_LENGTH_MAX
    instance.maxother = FORMAT_ARGS_LENGTH_MAX
    instance.maxset = _ARGUMENT_ITEMS_MAX
    instance.maxstring = FORMAT_ARGS_LENGTH_MAX
    instance.maxtuple = _ARGUMENT_ITEMS_MAX

    return instance


def _arguments_text(args: tuple, kwargs: dict) -> str:
    if not isinstance(args, tuple):
        message = f'args must be a tuple, not {type(args).__name__}'
        raise TypeError(message)

    if not isinstance(kwargs, dict):
        message = f'kwargs must be a dict, not {type(kwargs).__name__}'
        raise TypeError(message)

    representer = _arguments_reprlib()
    parts = [representer.repr(argument) for argument in args]

    parts.extend(f'{key}={representer.repr(value)}' for key, value in kwargs.items())
    text = ', '.join(parts)

    if len(text) > FORMAT_ARGS_LENGTH_MAX:
        text = text[:FORMAT_ARGS_LENGTH_MAX] + '...'

    return text


def _call_record(
    calls: list,
    *,
    alias: str,
    args: tuple,
    duration_ns: int,
    hit: bool,
    kwargs: dict,
    method: CacheMethod,
) -> None:
    if not isinstance(method, CacheMethod):
        message = f'method must be a CacheMethod: {method!r}'
        raise TypeError(message)

    if not isinstance(hit, bool):
        message = f'hit must be a bool: {hit!r}'
        raise TypeError(message)

    if duration_ns < 0:
        message = f'duration_ns must not be negative: {duration_ns}'
        raise ValueError(message)

    if len(calls) >= CACHE_CALLS_MAX:
        return

    call = {
        'alias': alias,
        'args': _arguments_text(args, kwargs),
        'duration_ms': round(duration_ns / 1_000_000, 2),
        'hit': hit,
        'method': method.upper(),
    }

    calls.append(call)


def _call_tracked(
    original: Callable,
    *,
    alias: str,
    args: tuple,
    calls: list,
    kwargs: dict,
    method: CacheMethod,
) -> Any:
    if not callable(original):
        message = f'original must be callable, not {type(original).__name__}'
        raise TypeError(message)

    if not isinstance(calls, list):
        message = f'calls must be a list, not {type(calls).__name__}'
        raise TypeError(message)

    nested: list[CacheMethod] = []
    token = _active.set(nested)
    started_ns = time.perf_counter_ns()
    hit = False

    try:
        if method is CacheMethod.GET:
            result, hit = _get_tracked(original, args, kwargs)
        else:
            result = original(*args, **kwargs)

            hit = _hit_resolve_guarded(
                method,
                args=args,
                kwargs=kwargs,
                nested=nested,
                result=result,
            )
    finally:
        _active.reset(token)

        _call_record(
            calls,
            alias=alias,
            args=args,
            duration_ns=time.perf_counter_ns() - started_ns,
            hit=hit,
            kwargs=kwargs,
            method=method,
        )

    return result


def _cache_patch(cache: object, alias: str) -> None:
    if not isinstance(alias, str):
        message = f'a cache alias must be text: {alias!r}'
        raise TypeError(message)

    if not alias:
        message = 'a cache alias must not be empty'
        raise ValueError(message)

    if getattr(cache, '_kaleidoscope_patched', False):
        return

    with _patch_lock:
        if getattr(cache, '_kaleidoscope_patched', False):
            return

        for method in CacheMethod:
            original = getattr(cache, method, None)

            if not callable(original):
                continue

            wrapper = _wrapper_build(original, method=method, alias=alias)

            setattr(cache, method, wrapper)

        cache._kaleidoscope_patched = True  # ty:ignore[unresolved-attribute]

        if _is_weakly_referable(cache):
            _caches_patched().add(cache)


def _cache_unpatch(cache: object) -> None:
    attributes = vars(cache)

    for method in CacheMethod:
        attributes.pop(method, None)

    attributes.pop('_kaleidoscope_patched', None)


def _caches_patch() -> None:
    for alias in list(caches)[:CACHES_MAX]:
        _cache_patch(caches[alias], alias)


@functools.cache
def _caches_patched() -> weakref.WeakSet:
    return weakref.WeakSet()


def _caches_unpatch() -> None:
    patched = _caches_patched()

    with _patch_lock:
        for cache in list(patched):
            _cache_unpatch(cache)

        patched.clear()


def _get_tracked(original: Callable, args: tuple, kwargs: dict) -> tuple[object, bool]:
    sentinel = object()

    if len(args) > 1:
        default = args[1]
        arguments = (args[0], sentinel, *args[2:])
        keywords = kwargs
    else:
        default = kwargs.get('default')
        arguments = args
        keywords = {**kwargs, 'default': sentinel}

    result = original(*arguments, **keywords)

    if result is sentinel:
        return default, False

    return result, True


def _hit_resolve(
    method: CacheMethod,
    *,
    args: tuple,
    kwargs: dict,
    nested: list[CacheMethod],
    result: object,
) -> bool:
    if not isinstance(method, CacheMethod):
        message = f'method must be a CacheMethod: {method!r}'
        raise TypeError(message)

    if not isinstance(nested, list):
        message = f'nested must be a list, not {type(nested).__name__}'
        raise TypeError(message)

    if method is CacheMethod.HAS_KEY:
        return bool(result)

    if method is CacheMethod.GET_OR_SET:
        return _NESTED_WRITES.isdisjoint(nested)

    if method is CacheMethod.GET_MANY:
        keys = args[0] if args else kwargs.get('keys', ())

        if not hasattr(keys, '__len__'):
            return bool(result)

        return len(result) == len(keys)  # ty:ignore[invalid-argument-type]

    return False


def _hit_resolve_guarded(
    method: CacheMethod,
    *,
    args: tuple,
    kwargs: dict,
    nested: list[CacheMethod],
    result: object,
) -> bool:
    try:
        hit = _hit_resolve(method, args=args, kwargs=kwargs, nested=nested, result=result)
    except Exception:
        logger.exception('Kaleidoscope could not tell whether a cache %s call hit', method.upper())
        hit = False

    return hit


def _is_weakly_referable(value: object) -> bool:
    try:
        weakref.ref(value)
    except TypeError:
        return False

    return True


def _hits_misses(calls: list[dict]) -> HitsMisses:
    if not isinstance(calls, list):
        message = f'calls must be a list, not {type(calls).__name__}'
        raise TypeError(message)

    hits = 0
    misses = 0

    for call in calls:
        if call['hit']:
            hits += 1
        elif call['method'] in _READ_METHOD_NAMES:
            misses += 1

    return HitsMisses(hits, misses)


def _wrapper_build(original: Callable, *, alias: str, method: CacheMethod) -> Callable:
    if not callable(original):
        message = f'original must be callable, not {type(original).__name__}'
        raise TypeError(message)

    if not isinstance(method, CacheMethod):
        message = f'method must be a CacheMethod: {method!r}'
        raise TypeError(message)

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        calls = _collecting.get(None)

        if calls is None:
            return original(*args, **kwargs)

        active = _active.get(None)

        if active is not None:
            active.append(method)

            return original(*args, **kwargs)

        return _call_tracked(
            original,
            alias=alias,
            args=args,
            calls=calls,
            kwargs=kwargs,
            method=method,
        )

    return wrapper


class CachePanel(Panel, Installable, RequestHook, ResponseHook):
    panel_id = 'cache'
    title = 'Cache'

    def __init__(self) -> None:
        super().__init__()

        self._calls: list[dict] = []

    def get_data(self) -> dict:
        calls = self._calls
        outcome = _hits_misses(calls)

        return {
            'calls': calls,
            'count': len(calls),
            'hits': outcome.hits,
            'misses': outcome.misses,
            'total_time': round(sum(call['duration_ms'] for call in calls), 2),
        }

    def get_summary(self) -> str:
        calls = self._calls

        if not calls:
            return '0 calls'

        outcome = _hits_misses(calls)

        if outcome.hits + outcome.misses == 0:
            return f'{len(calls)} calls'

        return f'{len(calls)} calls, {outcome.hits} hits, {outcome.misses} misses'

    def install(self) -> None:
        return

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request
        _ = context

        _caches_patch()
        _collecting.set([])

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

        calls = list(_collecting.get(None) or [])

        _collecting.set(None)

        if context.is_ajax:
            kept = (self._calls + calls)[-CACHE_CALLS_MAX:]
        else:
            kept = calls

        if len(kept) > CACHE_CALLS_MAX:
            message = f'{self.title} holds {len(kept)} calls, over the limit of {CACHE_CALLS_MAX}'
            raise RuntimeError(message)

        self._calls = kept

    def uninstall(self) -> None:
        _caches_unpatch()
