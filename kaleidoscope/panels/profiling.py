from __future__ import annotations

import threading

from typing import TYPE_CHECKING

from django.http import HttpResponse

from kaleidoscope.constants import ProfilingAction, StateKey
from kaleidoscope.panel import Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpRequest

    from kaleidoscope.context import KaleidoscopeContext

try:
    from pyinstrument import Profiler
    HAS_PYINSTRUMENT = True
except ImportError:
    HAS_PYINSTRUMENT = False


class ProfilingPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'profiling'
    title = 'Profiling'
    default_enabled = False
    isolate = True

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}
        self._lock = threading.Lock()

    def get_data(self) -> dict:
        with self._lock:
            data = dict(self._data)

        if not HAS_PYINSTRUMENT:
            data['error'] = 'pyinstrument is not installed. Run: pip install pyinstrument'

        return data

    def get_summary(self) -> str:
        with self._lock:
            duration = self._data.get('duration_ms', 0)

        if duration:
            return f'{duration:.0f} ms'

        return ''

    def handle_action(self, action: str, request: HttpRequest) -> HttpResponse | None:
        _ = request

        if action == ProfilingAction.HTML:
            with self._lock:
                html = self._data.get('html', '')

            if not html:
                html = (
                    '<html><body><p>No profile captured yet. '
                    'Navigate to a page with profiling enabled.</p></body></html>'
                )

            return HttpResponse(html, content_type='text/html')

        return None

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request

        if not HAS_PYINSTRUMENT:
            return

        if context.is_ajax:
            return

        profiler = Profiler()
        profiler.start()
        context.state[StateKey.PROFILER] = profiler

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        _ = request
        _ = response

        profiler = context.state.get(StateKey.PROFILER)

        if not profiler:
            return

        try:
            profiler.stop()
        except RuntimeError:
            with self._lock:
                self._data = {
                    'duration_ms': 0,
                    'has_data': False,
                    'html': '',
                    'text': 'Profiler stop failed: profiler was not running.',
                }

            return

        session = profiler.last_session

        if not session:
            return

        duration_ms = session.duration * 1000

        try:
            text = profiler.output_text(unicode=True, color=False)
        except Exception as exception:
            text = f'Profile captured: {duration_ms:.2f}ms (text output failed: {exception})'

        try:
            html = profiler.output_html()
        except Exception as exception:
            html = (
                f'<html><body><p>Profile captured: {duration_ms:.2f}ms '
                f'(HTML output failed: {exception})</p></body></html>'
            )

        with self._lock:
            self._data = {
                'duration_ms': round(duration_ms, 2),
                'has_data': True,
                'html': html,
                'text': text,
            }
