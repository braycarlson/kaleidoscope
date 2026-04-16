from __future__ import annotations

from typing import TYPE_CHECKING

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.conf import settings

from kaleidoscope.auth import AuthBackend
from kaleidoscope.constants import KALEIDOSCOPE_URL_PREFIX
from kaleidoscope.container import ServiceContainer
from kaleidoscope.context import create_context
from kaleidoscope.injector import ResponseInjector
from kaleidoscope.normalizer import SqlNormalizer
from kaleidoscope.processor import RequestProcessor
from kaleidoscope.registry import PanelRegistry
from kaleidoscope.router import Router
from kaleidoscope.store import QueryStore

if TYPE_CHECKING:
    from typing import Callable

    from django.http import HttpRequest, HttpResponse


class KaleidoscopeMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.async_mode = iscoroutinefunction(self.get_response)

        if self.async_mode:
            markcoroutinefunction(self)  # ty:ignore[invalid-argument-type]

        self._auth = AuthBackend()
        self._container = ServiceContainer()

        sql_normalizer = SqlNormalizer()
        self._container.register(SqlNormalizer, sql_normalizer)
        self._container.register(QueryStore, QueryStore(sql_normalizer))

        self._registry = PanelRegistry(self._container)
        self._processor = RequestProcessor(self._registry)
        self._router = Router(self._registry)
        self._injector = ResponseInjector()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if self.async_mode:
            return self.__acall__(request)  # ty:ignore[invalid-return-type]

        is_authorized = self._auth.check(request)

        if request.path.startswith(KALEIDOSCOPE_URL_PREFIX):
            return self._router.dispatch(request, is_authorized)

        if not is_authorized:
            return self.get_response(request)

        if self._should_skip(request):
            return self.get_response(request)

        context = create_context(is_ajax=self._is_ajax(request), asgi=False)
        self._processor.process_request(request, context)
        response = self.get_response(request)
        self._processor.process_response(request, response, context)

        return self._injector.process(request, response, context, self._registry)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        is_authorized = await self._auth.acheck(request)

        if request.path.startswith(KALEIDOSCOPE_URL_PREFIX):
            return self._router.dispatch(request, is_authorized)

        if not is_authorized:
            return await self.get_response(request)  # ty:ignore[invalid-await]

        if self._should_skip(request):
            return await self.get_response(request)  # ty:ignore[invalid-await]

        context = create_context(is_ajax=self._is_ajax(request), asgi=True)
        await self._processor.aprocess_request(request, context)

        response = await self.get_response(request)  # ty:ignore[invalid-await]
        await self._processor.aprocess_response(request, response, context)

        return self._injector.process(request, response, context, self._registry)

    def _is_ajax(self, request: HttpRequest) -> bool:
        requested_with = request.headers.get('X-Requested-With')

        if requested_with == 'XMLHttpRequest':
            return True

        sec_fetch_dest = request.headers.get('Sec-Fetch-Dest')

        if sec_fetch_dest:
            return sec_fetch_dest == 'empty'

        accept = request.headers.get('Accept', '')

        return bool(accept and 'text/html' not in accept)

    def _should_skip(self, request: HttpRequest) -> bool:
        ignore_paths = getattr(settings, 'KALEIDOSCOPE_IGNORE_PATHS', [])
        return any(request.path.startswith(path) for path in ignore_paths)
