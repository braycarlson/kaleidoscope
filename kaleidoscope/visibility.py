from __future__ import annotations

import logging

from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync, iscoroutinefunction, sync_to_async
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from typing import Callable


logger = logging.getLogger(__name__)


def _request_validate(request: object) -> None:
    if not isinstance(request, HttpRequest):
        message = f'the show callback needs an HttpRequest, not {type(request).__name__}'
        raise TypeError(message)


def _show_callback() -> Callable:
    path = getattr(settings, 'KALEIDOSCOPE_SHOW_CALLBACK', None)

    if path is None:
        return _show_default

    if not isinstance(path, str):
        message = f'KALEIDOSCOPE_SHOW_CALLBACK must be a dotted path, not {type(path).__name__}'
        raise ImproperlyConfigured(message)

    callback = import_string(path)

    if not callable(callback):
        message = f'KALEIDOSCOPE_SHOW_CALLBACK {path!r} names a {type(callback).__name__}'
        raise ImproperlyConfigured(message)

    return callback


def _show_default(request: HttpRequest) -> bool:
    _request_validate(request)

    if not settings.DEBUG:
        return False

    return request.META.get('REMOTE_ADDR') in getattr(settings, 'INTERNAL_IPS', ())


class Visibility:
    def __init__(self) -> None:
        callback = _show_callback()

        if iscoroutinefunction(callback):  # ty:ignore[deprecated]
            self._check = async_to_sync(callback)
            self._acheck = callback
        else:
            self._check = callback
            self._acheck = sync_to_async(callback)

    def check(self, request: HttpRequest) -> bool:
        _request_validate(request)

        try:
            shown = self._check(request)
        except Exception:
            logger.exception('Kaleidoscope show callback failed, hiding the toolbar')
            shown = False

        return bool(shown)

    async def acheck(self, request: HttpRequest) -> bool:
        _request_validate(request)

        try:
            shown = await self._acheck(request)
        except Exception:
            logger.exception('Kaleidoscope show callback failed, hiding the toolbar')
            shown = False

        return bool(shown)
