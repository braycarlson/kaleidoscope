from __future__ import annotations

import functools
import threading

from typing import TYPE_CHECKING

from kaleidoscope.constants import StateKey
from kaleidoscope.normalizer import PathShortener
from kaleidoscope.panel import Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext


_path_shortener = PathShortener(max_length=20)


class RequestPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'request'
    title = 'Request'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}
        self._lock = threading.Lock()

    def get_data(self) -> dict:
        with self._lock:
            return dict(self._data)

    def get_summary(self) -> str:
        with self._lock:
            method = self._data.get('method', '')
            status = self._data.get('status_code', '')
            path = self._data.get('path', '')

        if not method:
            return ''

        short_path = _path_shortener.shorten_url(path)

        return f'{method} {status} {short_path}'

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        context.state[StateKey.REQUEST_DATA] = {
            'content_type': request.content_type or '',
            'cookies': dict(request.COOKIES),
            'get': dict(request.GET),
            'headers': dict(request.headers),
            'method': request.method,
            'path': request.get_full_path(),
            'post': dict(request.POST),
        }

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        if context.is_ajax:
            return

        data = context.state.get(StateKey.REQUEST_DATA)

        if not data:
            return

        data['response_headers'] = dict(response.items())
        data['status_code'] = response.status_code

        if hasattr(request, 'resolver_match') and request.resolver_match:
            match = request.resolver_match
            func = match.func

            while isinstance(func, functools.partial):
                func = func.func

            data['view'] = {
                'args': list(match.args),
                'func': f'{func.__module__}.{func.__qualname__}',
                'kwargs': dict(match.kwargs),
                'route': getattr(match, 'route', ''),
                'url_name': match.url_name or '',
                'view_name': match.view_name or '',
            }

        with self._lock:
            self._data = data
