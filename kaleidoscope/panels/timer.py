from __future__ import annotations

import threading
import time

from typing import TYPE_CHECKING

from kaleidoscope.constants import StateKey
from kaleidoscope.panel import Panel, RequestHook, ResponseHook, ServerTimingMetric

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext


class TimerPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'timer'
    title = 'Timer'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}
        self._lock = threading.Lock()

    def get_data(self) -> dict:
        with self._lock:
            return dict(self._data)

    def get_server_timing(self) -> list[ServerTimingMetric]:
        with self._lock:
            total = self._data.get('total_ms', 0)

        if total:
            return [ServerTimingMetric(key='total', description='Total', duration=total)]

        return []

    def get_summary(self) -> str:
        with self._lock:
            total = self._data.get('total_ms', 0)
            method = self._data.get('method', '')

        if total:
            return f'{method} {total:.0f} ms'

        return ''

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request
        context.state[StateKey.TIMER_START] = time.perf_counter_ns()

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        if context.is_ajax:
            return

        start = context.state.get(StateKey.TIMER_START)

        if start is None:
            return

        total = (time.perf_counter_ns() - start) / 1_000_000

        data = {
            'asgi': context.asgi,
            'content_type': response.get('Content-Type', ''),
            'method': request.method,
            'path': request.get_full_path(),
            'status_code': response.status_code,
            'total_ms': round(total, 2),
        }

        with self._lock:
            self._data = data
