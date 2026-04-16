from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from kaleidoscope.constants import INJECTABLE_CONTENT_MAX, KALEIDOSCOPE_URL_PREFIX, Header

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext
    from kaleidoscope.registry import PanelRegistry


TEMPLATE_DIR = Path(__file__).parent / 'templates'

_HTML_TYPES = ('text/html', 'application/xhtml+xml')
_INJECTABLE_STATUS_RANGE = range(200, 300)


class ResponseInjector:
    def __init__(self) -> None:
        template_path = TEMPLATE_DIR / 'shell.html'
        self._shell_template = template_path.read_text(encoding='utf-8')

    def process(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
        registry: PanelRegistry,
    ) -> HttpResponse:
        self._add_server_timing(response, registry)
        response[str(Header.REQUEST_ID)] = context.request_id

        if not context.is_ajax and self._is_injectable(response):
            self._inject(request, response)

        return response

    def _add_server_timing(self, response: HttpResponse, registry: PanelRegistry) -> None:
        parts = []

        for panel in registry.panels.values():
            if not panel.enabled:
                continue

            for metric in panel.get_server_timing():
                entry = f'{panel.panel_id}_{metric.key};dur={metric.duration:.2f};desc="{metric.description}"'
                parts.append(entry)

        if not parts:
            return

        header = ', '.join(parts)
        existing = response.get(str(Header.SERVER_TIMING), '')

        if existing:
            response[str(Header.SERVER_TIMING)] = f'{existing}, {header}'
        else:
            response[str(Header.SERVER_TIMING)] = header

    def _build_shell(self, request: HttpRequest) -> str:
        nonce = self._get_csp_nonce(request)

        if nonce is None:
            return self._shell_template

        return self._shell_template.replace('<script ', f'<script nonce="{nonce}" ')

    def _get_csp_nonce(self, request: HttpRequest) -> str | None:
        try:
            import django  # noqa: PLC0415

            if django.VERSION >= (6, 0):
                from django.middleware.csp import get_nonce  # noqa: PLC0415

                return get_nonce(request)
        except ImportError:
            pass

        nonce = getattr(request, '_csp_nonce', None)

        if nonce:
            return nonce

        csp_middleware_nonce = getattr(request, 'csp_nonce', None)

        if csp_middleware_nonce:
            return csp_middleware_nonce

        return None

    def _inject(self, request: HttpRequest, response: HttpResponse) -> None:
        if len(response.content) > INJECTABLE_CONTENT_MAX:
            return

        content = response.content.decode(response.charset)
        script_path = KALEIDOSCOPE_URL_PREFIX + 'static/kaleidoscope.js'

        if script_path in content:
            return

        parts = content.rsplit('</body>', 1)

        if len(parts) != 2:
            return

        shell = self._build_shell(request)
        content = parts[0] + shell + '</body>' + parts[1]
        response.content = content.encode(response.charset)
        response['Content-Length'] = len(response.content)

    def _is_injectable(self, response: HttpResponse) -> bool:
        if getattr(response, 'streaming', False):
            return False

        if response.status_code not in _INJECTABLE_STATUS_RANGE:
            return False

        content_encoding = response.get('Content-Encoding', '')

        if content_encoding:
            return False

        content_type = response.get('Content-Type', '').split(';')[0].strip()

        if content_type not in _HTML_TYPES:
            return False

        return hasattr(response, 'content')
