from __future__ import annotations

import functools
import linecache
import logging
import re
import sys
import time
import weakref

import django.dispatch

from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType, ModuleType
from typing import TYPE_CHECKING

from django.utils.module_loading import import_string

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Installable, Panel, RequestHook, ResponseHook
from kaleidoscope.patch import method_patch, method_unpatch, patch_marked
from kaleidoscope.store import user_frame_innermost

if TYPE_CHECKING:
    from typing import Callable

    from django.http import HttpRequest, HttpResponse


BUILTIN_SIGNALS = MappingProxyType({
    'django.contrib.auth.signals.user_logged_in': 'user_logged_in',
    'django.contrib.auth.signals.user_logged_out': 'user_logged_out',
    'django.contrib.auth.signals.user_login_failed': 'user_login_failed',
    'django.core.signals.got_request_exception': 'got_request_exception',
    'django.core.signals.request_finished': 'request_finished',
    'django.core.signals.request_started': 'request_started',
    'django.core.signals.setting_changed': 'setting_changed',
    'django.db.models.signals.m2m_changed': 'm2m_changed',
    'django.db.models.signals.post_delete': 'post_delete',
    'django.db.models.signals.post_init': 'post_init',
    'django.db.models.signals.post_migrate': 'post_migrate',
    'django.db.models.signals.post_save': 'post_save',
    'django.db.models.signals.pre_delete': 'pre_delete',
    'django.db.models.signals.pre_init': 'pre_init',
    'django.db.models.signals.pre_migrate': 'pre_migrate',
    'django.db.models.signals.pre_save': 'pre_save',
})

RECEIVERS_PER_SIGNAL_MAX = 512
SEND_GROUPS_MAX = 1_024
SEND_METHODS_ASYNC = MappingProxyType({'asend': False, 'asend_robust': True})
SEND_METHODS_SYNC = MappingProxyType({'send': False, 'send_robust': True})
SIGNAL_ATTRIBUTES_MAX = 2_000_000
SIGNAL_MODULES_MAX = 20_000
SIGNAL_NAME_UNKNOWN = '(unnamed signal)'
SIGNAL_SENDS_MAX = 50_000
SIGNAL_SOURCE_LINES_MAX = 100_000

_RECEIVER_DEAD = MappingProxyType({
    'module': '',
    'name': '(dead reference)',
    'path': '(dead reference)',
})

_collecting: ContextVar[SendLog | None] = ContextVar('_signal_collecting', default=None)
_depth: ContextVar[int] = ContextVar('_signal_depth', default=0)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SendGroup:
    count: int
    duration_ns: int
    duration_outermost_ns: int
    errors: int
    receivers: list
    sender: object
    signal: object
    site: dict | None


@dataclass(slots=True)
class SendLog:
    closed: bool
    count: int
    groups: dict[tuple[int, int], SendGroup]


def _errors_counted(responses: list | None, *, robust: bool) -> int:
    if responses is None:
        return 1

    if not robust:
        return 0

    return sum(1 for _receiver, response in responses if issubclass(type(response), Exception))


def _group_duration_ns(group: SendGroup) -> int:
    return group.duration_ns


def _receiver_described(receiver: object) -> dict:
    if isinstance(receiver, weakref.ReferenceType):
        receiver = receiver()

        if receiver is None:
            return dict(_RECEIVER_DEAD)

    func = getattr(receiver, '__wrapped__', receiver)
    owner = getattr(func, '__self__', None)

    if owner is None:
        module = getattr(func, '__module__', '')
        qualname = getattr(func, '__qualname__', getattr(func, '__name__', str(func)))
    else:
        module = owner.__class__.__module__
        qualname = f'{owner.__class__.__qualname__}.{getattr(func, "__name__", str(func))}'

    return {
        'module': module,
        'name': qualname,
        'path': f'{module}.{qualname}',
    }


def _receivers_responded(responses: list | None) -> list:
    if responses is None:
        return []

    return [response[0] for response in responses[:RECEIVERS_PER_SIGNAL_MAX]]


def _send_async_wrapper_build(original: Callable, *, robust: bool) -> Callable:
    if not callable(original):
        message = f'original must be callable, not {type(original).__name__}'
        raise TypeError(message)

    @functools.wraps(original)
    async def send_tracked(signal: object, sender: object, **named: object) -> list:
        log = _collecting.get(None)

        if log is None:
            return await original(signal, sender, **named)

        depth = _depth.get()
        token = _depth.set(depth + 1)
        started_ns = time.perf_counter_ns()
        responses = None

        try:
            responses = await original(signal, sender, **named)
        finally:
            duration_ns = time.perf_counter_ns() - started_ns

            _depth.reset(token)

            try:
                _send_record(
                    log,
                    depth=depth,
                    duration_ns=duration_ns,
                    responses=responses,
                    robust=robust,
                    sender=sender,
                    signal=signal,
                )
            except Exception:
                logger.exception('Kaleidoscope could not record a signal send')

        return responses

    return patch_marked(send_tracked)


def _send_described(group: SendGroup, paths: dict[object, str]) -> dict:
    path = paths.get(group.signal, '')
    receivers = [_receiver_described(receiver)['path'] for receiver in group.receivers]

    return {
        'count': group.count,
        'duration_ms': round(group.duration_ns / 1_000_000, 2),
        'errors': group.errors,
        'module': path,
        'name': path.rsplit('.', 1)[-1] if path else SIGNAL_NAME_UNKNOWN,
        'receivers': receivers,
        'sender': _sender_label(group.sender),
        'site': group.site,
    }


def _send_record(
    log: SendLog,
    *,
    depth: int,
    duration_ns: int,
    responses: list | None,
    robust: bool,
    sender: object,
    signal: object,
) -> None:
    if log.closed:
        return

    if log.count >= SIGNAL_SENDS_MAX:
        return

    key = (id(signal), id(sender))
    group = log.groups.get(key)

    if group is None:
        if len(log.groups) >= SEND_GROUPS_MAX:
            return

        group = SendGroup(
            count=0,
            duration_ns=0,
            duration_outermost_ns=0,
            errors=0,
            receivers=_receivers_responded(responses),
            sender=sender,
            signal=signal,
            site=user_frame_innermost(),
        )

        log.groups[key] = group

    log.count += 1
    group.count += 1
    group.duration_ns += duration_ns
    group.errors += _errors_counted(responses, robust=robust)

    if depth == 0:
        group.duration_outermost_ns += duration_ns


def _send_wrapper_build(original: Callable, *, robust: bool) -> Callable:
    if not callable(original):
        message = f'original must be callable, not {type(original).__name__}'
        raise TypeError(message)

    @functools.wraps(original)
    def send_tracked(signal: object, sender: object, **named: object) -> list:
        log = _collecting.get(None)

        if log is None:
            return original(signal, sender, **named)

        depth = _depth.get()
        token = _depth.set(depth + 1)
        started_ns = time.perf_counter_ns()
        responses = None

        try:
            responses = original(signal, sender, **named)
        finally:
            duration_ns = time.perf_counter_ns() - started_ns

            _depth.reset(token)

            try:
                _send_record(
                    log,
                    depth=depth,
                    duration_ns=duration_ns,
                    responses=responses,
                    robust=robust,
                    sender=sender,
                    signal=signal,
                )
            except Exception:
                logger.exception('Kaleidoscope could not record a signal send')

        return responses

    return patch_marked(send_tracked)


def _sender_label(sender: object) -> str:
    if sender is None:
        return ''

    if issubclass(type(sender), type):
        return f'{getattr(sender, "__module__", "")}.{getattr(sender, "__qualname__", "")}'

    return type(sender).__qualname__


def _sends_merged(log: SendLog, addition: SendLog) -> None:
    for key, group in addition.groups.items():
        existing = log.groups.get(key)

        if existing is not None:
            existing.count += group.count
            existing.duration_ns += group.duration_ns
            existing.duration_outermost_ns += group.duration_outermost_ns
            existing.errors += group.errors
        elif len(log.groups) < SEND_GROUPS_MAX:
            log.groups[key] = group

    log.count += addition.count


def _signal_candidates() -> dict[object, list[str]]:
    candidates: dict[object, list[str]] = {}
    modules = list(sys.modules.items())[:SIGNAL_MODULES_MAX]
    attributes_seen = 0

    for module_name, module in modules:
        if not issubclass(type(module), ModuleType):
            continue

        try:
            namespace = list(vars(module).items())
        except TypeError:
            continue

        for attribute, value in namespace:
            attributes_seen += 1

            if attributes_seen > SIGNAL_ATTRIBUTES_MAX:
                return candidates

            if issubclass(type(value), django.dispatch.Signal):
                candidates.setdefault(value, []).append(f'{module_name}.{attribute}')

    return candidates


def _signal_described(signal: object, path: str) -> dict:
    if not isinstance(path, str):
        message = f'a signal path must be text: {path!r}'
        raise TypeError(message)

    if not path:
        message = 'a signal needs a path'
        raise ValueError(message)

    entries = list(getattr(signal, 'receivers', []))[:RECEIVERS_PER_SIGNAL_MAX]
    receivers = [_receiver_described(entry[1]) for entry in entries]

    return {
        'module': path,
        'name': path.rsplit('.', 1)[-1],
        'receiver_count': len(receivers),
        'receivers': receivers,
    }


def _signal_order(signal: dict) -> tuple[str, str]:
    return signal['name'], signal['module']


def _signal_path_assigns(path: str) -> bool:
    module_name, attribute = path.rsplit('.', 1)
    filename = getattr(sys.modules.get(module_name), '__file__', None)

    if not isinstance(filename, str):
        return False

    pattern = re.compile(rf'{re.escape(attribute)}\s*(?::[^=\n]+)?=(?!=)')
    lines = linecache.getlines(filename)[:SIGNAL_SOURCE_LINES_MAX]

    return any(pattern.match(line) for line in lines)


def _signal_path_chosen(found: list[str]) -> str:
    if len(found) == 1:
        return found[0]

    defining = [path for path in found if _signal_path_assigns(path)]

    return min(defining or found, key=_signal_path_rank)


def _signal_path_rank(path: str) -> tuple[bool, int, str]:
    module_name = path.rsplit('.', 1)[0]
    defined_in_signals = module_name.rsplit('.', 1)[-1] == 'signals'

    return not defined_in_signals, path.count('.'), path


def _signal_paths() -> dict[object, str]:
    paths: dict[object, str] = {}

    for path in BUILTIN_SIGNALS:
        try:
            signal = import_string(path)
        except ImportError:
            continue

        if issubclass(type(signal), django.dispatch.Signal):
            paths[signal] = path

    for signal, found in _signal_candidates().items():
        if signal not in paths:
            paths[signal] = _signal_path_chosen(found)

    return paths


def _signals_described(paths: dict[object, str]) -> dict:
    signals = [_signal_described(signal, path) for signal, path in paths.items()]

    signals.sort(key=_signal_order)

    return {
        'count': len(signals),
        'signals': signals,
        'total_receivers': sum(signal['receiver_count'] for signal in signals),
    }


class SignalsPanel(Panel, Installable, RequestHook, ResponseHook):
    panel_id = 'signals'
    title = 'Signals'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict | None = None
        self._log = SendLog(closed=False, count=0, groups={})

    def get_data(self) -> dict:
        paths = _signal_paths()
        groups = sorted(self._log.groups.values(), key=_group_duration_ns, reverse=True)
        time_ns = sum(group.duration_outermost_ns for group in groups)

        data = {
            **_signals_described(paths),
            'send_count': self._log.count,
            'send_time': round(time_ns / 1_000_000, 2),
            'sends': [_send_described(group, paths) for group in groups],
        }

        self._data = data

        return data

    def get_summary(self) -> str:
        log = self._log

        if log.count:
            time_ns = sum(group.duration_outermost_ns for group in log.groups.values())

            return f'{log.count} sends, {round(time_ns / 1_000_000, 2)} ms'

        data = self._data

        if data is None:
            data = self.get_data()

        return f'{data["total_receivers"]} receivers, {data["count"]} signals'

    def install(self) -> None:
        for name, robust in SEND_METHODS_ASYNC.items():
            build = functools.partial(_send_async_wrapper_build, robust=robust)

            method_patch(django.dispatch.Signal, name, build)

        for name, robust in SEND_METHODS_SYNC.items():
            build = functools.partial(_send_wrapper_build, robust=robust)

            method_patch(django.dispatch.Signal, name, build)

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request
        _ = context

        log = SendLog(closed=False, count=0, groups={})

        _collecting.set(log)

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

        log = _collecting.get(None)

        _collecting.set(None)

        if log is None:
            return

        log.closed = True

        if context.is_ajax:
            _sends_merged(self._log, log)

            return

        self._log = log

    def uninstall(self) -> None:
        for name in (*SEND_METHODS_ASYNC, *SEND_METHODS_SYNC):
            method_unpatch(django.dispatch.Signal, name)
