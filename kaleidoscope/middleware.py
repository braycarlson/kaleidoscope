from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING

from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseServerError
from django.urls import Resolver404, get_resolver

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.injector import ResponseInjector
from kaleidoscope.registry import PanelRegistry, panels_load
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX, Router
from kaleidoscope.visibility import Visibility

if TYPE_CHECKING:
    from typing import Callable

    from kaleidoscope.panel import Panel


STATUS_CLIENT_CLOSED_REQUEST = 499


def _is_ajax(request: HttpRequest) -> bool:
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True

    sec_fetch_dest = request.headers.get('Sec-Fetch-Dest')

    if sec_fetch_dest:
        return sec_fetch_dest != 'document'

    accept = request.headers.get('Accept', '')

    if not accept:
        return False

    return 'text/html' not in accept


def _is_ignored(request: HttpRequest) -> bool:
    ignore_paths = getattr(settings, 'KALEIDOSCOPE_IGNORE_PATHS', [])

    if not isinstance(ignore_paths, (list, tuple)):
        return False

    return any(request.path.startswith(path) for path in ignore_paths if isinstance(path, str))


def _panels_on_loop(request: HttpRequest, panels: list[Panel]) -> list[Panel]:
    following = [panel for panel in panels if panel.follows_view]

    if not following:
        return []

    if not _view_is_async(request):
        return []

    return following


def _view_is_async(request: HttpRequest) -> bool:
    resolver = get_resolver(getattr(request, 'urlconf', None))

    try:
        match = resolver.resolve(request.path_info)
    except Resolver404:
        return False

    return iscoroutinefunction(match.func)  # ty:ignore[deprecated]


class KaleidoscopeMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        if not callable(get_response):
            message = f'get_response must be callable: {get_response!r}'
            raise TypeError(message)

        self.get_response = get_response
        self.async_mode = iscoroutinefunction(get_response)  # ty:ignore[deprecated]

        if self.async_mode:
            markcoroutinefunction(self)  # ty:ignore[invalid-argument-type]

        self._injector = ResponseInjector()
        self._registry = PanelRegistry(panels_load())
        self._router = Router(self._registry)
        self._visibility = Visibility()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not isinstance(request, HttpRequest):
            message = f'the middleware needs an HttpRequest, not {type(request).__name__}'
            raise TypeError(message)

        if self.async_mode:
            return self.__acall__(request)  # ty:ignore[invalid-return-type]

        is_shown = self._visibility.check(request)

        if request.path.startswith(KALEIDOSCOPE_URL_PREFIX):
            return self._router.dispatch(request, is_shown)

        if not is_shown:
            return self.get_response(request)

        if _is_ignored(request):
            return self.get_response(request)

        panels = self._registry.active()
        context = KaleidoscopeContext(asgi=False, is_ajax=_is_ajax(request), panels=panels)

        self._registry.process_request(request, context, panels)

        try:
            response = self.get_response(request)
        except Exception:
            failure = HttpResponseServerError()

            self._registry.process_response(request, failure, context, panels)

            raise

        self._registry.process_response(request, response, context, panels)

        return self._injector.process(request, response, context)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        is_shown = await self._visibility.acheck(request)

        if request.path.startswith(KALEIDOSCOPE_URL_PREFIX):
            dispatch = sync_to_async(self._router.dispatch, thread_sensitive=True)

            return await dispatch(request, is_shown)

        if not is_shown:
            return await self.get_response(request)  # ty:ignore[invalid-await]

        if _is_ignored(request):
            return await self.get_response(request)  # ty:ignore[invalid-await]

        panels = self._registry.active()
        context = KaleidoscopeContext(asgi=True, is_ajax=_is_ajax(request), panels=panels)
        panels_loop = _panels_on_loop(request, panels)
        panels_worker = [panel for panel in panels if panel not in panels_loop]

        if len(panels_loop) + len(panels_worker) != len(panels):
            message = f'the panels on the loop are not among the active panels: {panels_loop!r}'
            raise RuntimeError(message)

        try:
            await self._arequest_process(request, context, panels_loop, panels_worker)
            response = await self.get_response(request)  # ty:ignore[invalid-await]
        except asyncio.CancelledError:
            cancelled = HttpResponse(status=STATUS_CLIENT_CLOSED_REQUEST)

            await self._aresponse_process(request, cancelled, context, panels_loop, panels_worker)

            raise
        except Exception:
            failure = HttpResponseServerError()

            await self._aresponse_process(request, failure, context, panels_loop, panels_worker)

            raise

        await self._aresponse_process(request, response, context, panels_loop, panels_worker)

        return self._injector.process(request, response, context)

    async def _arequest_process(
        self,
        request: HttpRequest,
        context: KaleidoscopeContext,
        panels_loop: list[Panel],
        panels_worker: list[Panel],
    ) -> None:
        if panels_worker:
            process_request = sync_to_async(self._registry.process_request, thread_sensitive=True)

            await process_request(request, context, panels_worker)

        self._registry.process_request(request, context, panels_loop)

    async def _aresponse_process(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
        panels_loop: list[Panel],
        panels_worker: list[Panel],
    ) -> None:
        self._registry.process_response(request, response, context, panels_loop)

        if panels_worker:
            process_response = sync_to_async(self._registry.process_response, thread_sensitive=True)

            await process_response(request, response, context, panels_worker)
