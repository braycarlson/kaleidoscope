from __future__ import annotations

from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync, iscoroutinefunction, sync_to_async
from django.conf import settings
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from typing import Callable

    from django.http import HttpRequest


def _default_show_kaleidoscope(request: HttpRequest) -> bool:
    return (
        settings.DEBUG
        and request.META.get('REMOTE_ADDR') in getattr(settings, 'INTERNAL_IPS', ())
    )


class AuthBackend:
    def __init__(self) -> None:
        self._callback = self._resolve_callback()
        self._is_coroutine = iscoroutinefunction(self._callback)
        self._sync = self._build_sync()
        self._async = self._build_async()

    def _resolve_callback(self) -> Callable:
        callback_path = getattr(settings, 'KALEIDOSCOPE_SHOW_CALLBACK', None)

        if callback_path is not None:
            return import_string(callback_path)

        return _default_show_kaleidoscope

    def _build_sync(self) -> Callable:
        if self._is_coroutine:
            return async_to_sync(self._callback)

        return self._callback

    def _build_async(self) -> Callable:
        if not self._is_coroutine:
            return sync_to_async(self._callback)

        return self._callback

    def check(self, request: HttpRequest) -> bool:
        return self._sync(request)

    async def acheck(self, request: HttpRequest) -> bool:
        return await self._async(request)
