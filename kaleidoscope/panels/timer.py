from __future__ import annotations

import time

from typing import TYPE_CHECKING

from django.http import HttpRequest, HttpResponseBase

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Panel, ResponseHook, ServerTimingMetric

if TYPE_CHECKING:
    from django.http import HttpResponse


class TimerPanel(Panel, ResponseHook):
    panel_id = 'timer'
    title = 'Timer'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}

    def get_data(self) -> dict:
        return dict(self._data)

    def get_server_timing(self, context: KaleidoscopeContext) -> list[ServerTimingMetric]:
        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        duration_ms = context.state.get(self.panel_id)

        if duration_ms is None:
            return []

        if duration_ms < 0:
            message = f'{self.title} measured a negative duration: {duration_ms}'
            raise RuntimeError(message)

        return [ServerTimingMetric(key='total', description='Total', duration=duration_ms)]

    def get_summary(self) -> str:
        data = self._data
        duration_ms = data.get('total_ms', 0)

        if duration_ms:
            return f'{data.get("method", "")} {duration_ms:.0f} ms'

        return ''

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

        duration_ms = round((time.perf_counter_ns() - context.started_ns) / 1_000_000, 2)

        if duration_ms < 0:
            message = f'{self.title} measured a negative duration: {duration_ms}'
            raise RuntimeError(message)

        context.state[self.panel_id] = duration_ms

        if context.is_ajax:
            return

        self._data = {
            'asgi': context.asgi,
            'content_type': response.get('Content-Type', ''),
            'method': request.method,
            'path': request.get_full_path(),
            'status_code': response.status_code,
            'total_ms': duration_ms,
        }
