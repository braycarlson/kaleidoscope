from __future__ import annotations

from typing import TYPE_CHECKING

from django.http import HttpResponse
from pyinstrument import Profiler

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpRequest


HTML_EMPTY = (
    '<html><body><p>No profile captured yet. '
    'Navigate to a page with profiling enabled.</p></body></html>'
)


def _profile_html(profiler: Profiler, duration_ms: float) -> str:
    if duration_ms < 0:
        message = f'duration_ms must not be negative: {duration_ms}'
        raise ValueError(message)

    try:
        html = profiler.output_html()
    except Exception as exception:
        html = (
            f'<html><body><p>Profile captured: {duration_ms:.2f}ms '
            f'(HTML output failed: {exception})</p></body></html>'
        )

    if not isinstance(html, str):
        message = f'the profiler rendered its HTML as a {type(html).__name__}, not text'
        raise TypeError(message)

    return html


def _profile_text(profiler: Profiler, duration_ms: float) -> str:
    if duration_ms < 0:
        message = f'duration_ms must not be negative: {duration_ms}'
        raise ValueError(message)

    try:
        text = profiler.output_text(unicode=True, color=False)
    except Exception as exception:
        text = f'Profile captured: {duration_ms:.2f}ms (text output failed: {exception})'

    if not isinstance(text, str):
        message = f'the profiler rendered its text as a {type(text).__name__}, not text'
        raise TypeError(message)

    return text


class ProfilingPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'profiling'
    title = 'Profiling'
    default_enabled = False
    follows_view = True
    isolate = True

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}

    def get_data(self) -> dict:
        return dict(self._data)

    def get_summary(self) -> str:
        duration_ms = self._data.get('duration_ms', 0)

        if duration_ms:
            return f'{duration_ms:.0f} ms'

        return ''

    def handle_action(self, action: str, request: HttpRequest) -> HttpResponse | None:
        _ = request

        if not isinstance(action, str):
            message = f'action must be text: {action!r}'
            raise TypeError(message)

        if action != 'html':
            return None

        html = self._data.get('html') or HTML_EMPTY
        response = HttpResponse(html, content_type='text/html')
        response['X-Frame-Options'] = 'SAMEORIGIN'

        return response

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request

        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        if context.is_ajax:
            return

        profiler = Profiler()

        profiler.start()

        context.state[self.panel_id] = profiler

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

        profiler = context.state.get(self.panel_id)

        if profiler is None:
            return

        try:
            profiler.stop()
        except RuntimeError:
            self._data = {
                'duration_ms': 0,
                'has_data': False,
                'html': '',
                'text': 'Profiler stop failed: profiler was not running.',
            }

            return

        session = profiler.last_session

        if session is None:
            return

        duration_ms = session.duration * 1000

        if duration_ms < 0:
            message = f'the profiler measured a negative duration: {duration_ms}'
            raise RuntimeError(message)

        self._data = {
            'duration_ms': round(duration_ms, 2),
            'has_data': True,
            'html': _profile_html(profiler, duration_ms),
            'text': _profile_text(profiler, duration_ms),
        }
