from __future__ import annotations

import functools
import json
import logging

from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpRequest, HttpResponseBase
from django.utils.module_loading import import_string

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Installable, Panel, RequestHook, ResponseHook
from kaleidoscope.patch import method_patch, method_unpatch, patch_marked
from kaleidoscope.serializer import preview

if TYPE_CHECKING:
    from typing import Callable

    from django.http import HttpResponse


PARTIAL_DEPTH_MAX = 32
PERMISSION_CHECKS_MAX = 10_000
PERMISSION_GROUPS_MAX = 1_024
PERMISSION_METHODS = MappingProxyType({'has_module_perms': 'module', 'has_perm': 'permission'})
PERMISSION_NAME_LENGTH_MAX = 200

PERMISSION_OWNERS = (
    'django.contrib.auth.models.AnonymousUser',
    'django.contrib.auth.models.PermissionsMixin',
)

SESSION_KEYS_MAX = 1_024
SUMMARY_PATH_LENGTH_MAX = 20
_checking: ContextVar[PermissionLog | None] = ContextVar('_permission_checking', default=None)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PermissionCheck:
    count: int
    kind: str
    name: str
    result: bool
    superuser: bool
    target: str

    def listed(self) -> dict:
        return {
            'count': self.count,
            'kind': self.kind,
            'name': self.name,
            'result': self.result,
            'superuser': self.superuser,
            'target': self.target,
        }


@dataclass(slots=True)
class PermissionLog:
    checks: dict[tuple[str, str, str, bool, bool], PermissionCheck]
    closed: bool
    count: int


def _check_record(
    log: PermissionLog,
    *,
    kind: str,
    name: object,
    result: object,
    target: object,
    user: object,
) -> None:
    if log.closed:
        return

    if log.count >= PERMISSION_CHECKS_MAX:
        return

    active = bool(getattr(user, 'is_active', False))
    superuser = active and bool(getattr(user, 'is_superuser', False))
    granted = bool(result)
    name_text = str(name)[:PERMISSION_NAME_LENGTH_MAX]
    target_label = _target_label(target)
    key = (kind, name_text, target_label, granted, superuser)
    check = log.checks.get(key)

    if check is None:
        if len(log.checks) >= PERMISSION_GROUPS_MAX:
            return

        check = PermissionCheck(
            count=0,
            kind=kind,
            name=name_text,
            result=granted,
            superuser=superuser,
            target=target_label,
        )

        log.checks[key] = check

    log.count += 1
    check.count += 1


def _check_name(arguments: tuple, keywords: dict) -> object:
    if arguments:
        return arguments[0]

    return keywords.get('perm', keywords.get('app_label', keywords.get('module')))


def _check_wrapper_build(original: Callable, *, kind: str) -> Callable:
    if not callable(original):
        message = f'original must be callable, not {type(original).__name__}'
        raise TypeError(message)

    @functools.wraps(original)
    def check_tracked(user: object, *arguments: object, **keywords: object) -> object:
        result = original(user, *arguments, **keywords)
        log = _checking.get(None)

        if log is None:
            return result

        name = _check_name(arguments, keywords)
        target = arguments[1] if len(arguments) > 1 else keywords.get('obj')

        try:
            _check_record(log, kind=kind, name=name, result=result, target=target, user=user)
        except Exception:
            logger.exception('Kaleidoscope could not record a permission check')

        return result

    return patch_marked(check_tracked)


def _json_safe(value: object) -> object:
    try:
        json.dumps(value, cls=DjangoJSONEncoder, allow_nan=False)
    except (OverflowError, RecursionError, TypeError, ValueError):
        return preview(value)

    return value


def _permission_owners() -> list[type]:
    if not apps.is_installed('django.contrib.auth'):
        return []

    return [import_string(path) for path in PERMISSION_OWNERS]


def _post_read(request: HttpRequest) -> dict:
    try:
        post = dict(request.POST)
    except Exception:
        logger.exception('Kaleidoscope could not read the POST data of %s', request.path)
        post = {}

    return post


def _session_described(request: HttpRequest) -> dict | None:
    session = getattr(request, 'session', None)

    if session is None:
        return None

    accessed = bool(getattr(session, 'accessed', False))
    modified = bool(getattr(session, 'modified', False))

    try:
        items = list(session.items())[:SESSION_KEYS_MAX]
        expire_at_browser_close = bool(session.get_expire_at_browser_close())
        expiry_age = int(session.get_expiry_age())
    except Exception:
        logger.exception('Kaleidoscope could not read the session of %s', request.path)
        items = []
        expire_at_browser_close = False
        expiry_age = 0
    finally:
        session.accessed = accessed

    return {
        'accessed': accessed,
        'backend': f'{type(session).__module__}.{type(session).__qualname__}',
        'expire_at_browser_close': expire_at_browser_close,
        'expiry_age': expiry_age,
        'items': {str(key): _json_safe(value) for key, value in items},
        'modified': modified,
    }


def _target_label(target: object) -> str:
    if target is None:
        return ''

    label = type(target).__qualname__
    key = getattr(target, 'pk', None)

    if key is None:
        return label

    return f'{label} {key}'


def _url_path_shortened(url: str, length_max: int) -> str:
    if not isinstance(url, str):
        message = f'url must be text: {url!r}'
        raise TypeError(message)

    if length_max < 3:
        message = f'length_max must leave room for an ellipsis: {length_max}'
        raise ValueError(message)

    path = urlparse(url).path

    if len(path) <= length_max:
        return path

    return path[:length_max - 3] + '...'


def _user_described(request: HttpRequest) -> dict | None:
    user = getattr(request, 'user', None)

    if user is None:
        return None

    try:
        key = getattr(user, 'pk', None)

        described = {
            'active': bool(getattr(user, 'is_active', False)),
            'authenticated': bool(getattr(user, 'is_authenticated', False)),
            'id': '' if key is None else str(key),
            'name': str(user),
            'staff': bool(getattr(user, 'is_staff', False)),
            'superuser': bool(getattr(user, 'is_superuser', False)),
        }
    except Exception:
        logger.exception('Kaleidoscope could not read the user of %s', request.path)
        described = None

    return described


def _view_describe(request: HttpRequest) -> dict | None:
    match = getattr(request, 'resolver_match', None)

    if not match:
        return None

    func = match.func

    for _ in range(PARTIAL_DEPTH_MAX):
        if not isinstance(func, functools.partial):
            break

        func = func.func

    target = getattr(func, 'view_class', func)
    module = getattr(target, '__module__', '') or ''
    qualname = getattr(target, '__qualname__', '') or type(target).__qualname__

    return {
        'args': [_json_safe(argument) for argument in match.args],
        'func': f'{module}.{qualname}',
        'kwargs': {key: _json_safe(value) for key, value in match.kwargs.items()},
        'route': getattr(match, 'route', '') or '',
        'url_name': match.url_name or '',
        'view_name': match.view_name or '',
    }


class RequestPanel(Panel, Installable, RequestHook, ResponseHook):
    panel_id = 'request'
    title = 'Request'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}

    def get_data(self) -> dict:
        return dict(self._data)

    def get_summary(self) -> str:
        data = self._data
        method = data.get('method', '')

        if not method:
            return ''

        path = _url_path_shortened(data.get('path', ''), SUMMARY_PATH_LENGTH_MAX)

        return f'{method} {data.get("status_code", "")} {path}'

    def install(self) -> None:
        for owner in _permission_owners():
            for name, kind in PERMISSION_METHODS.items():
                build = functools.partial(_check_wrapper_build, kind=kind)

                method_patch(owner, name, build)

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request
        _ = context

        log = PermissionLog(checks={}, closed=False, count=0)

        _checking.set(log)

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        if not isinstance(request, HttpRequest):
            message = f'{self.title} needs an HttpRequest, not {type(request).__name__}'
            raise TypeError(message)

        if not isinstance(response, HttpResponseBase):
            message = f'{self.title} needs an HttpResponse, not {type(response).__name__}'
            raise TypeError(message)

        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        log = _checking.get(None)

        _checking.set(None)

        if log is not None:
            log.closed = True

        if context.is_ajax:
            return

        checks = [] if log is None else [check.listed() for check in log.checks.values()]

        data = {
            'content_type': request.content_type or '',
            'cookies': dict(request.COOKIES),
            'get': dict(request.GET),
            'headers': dict(request.headers),
            'method': request.method,
            'path': request.get_full_path(),
            'permissions': checks,
            'post': _post_read(request),
            'response_headers': dict(response.items()),
            'session': _session_described(request),
            'status_code': response.status_code,
            'user': _user_described(request),
        }

        view = _view_describe(request)

        if view is not None:
            data['view'] = view

        self._data = data

    def uninstall(self) -> None:
        for owner in _permission_owners():
            for name in PERMISSION_METHODS:
                method_unpatch(owner, name)
