from __future__ import annotations

import logging
import math
import os
import re
import uuid

from pathlib import Path
from typing import TYPE_CHECKING

from django.http import HttpRequest, HttpResponseBase
from django.utils.html import escape

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Panel, ServerTimingMetric
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX

if TYPE_CHECKING:
    from django.http import HttpResponse


ENVIRONMENT_LAUNCH = 'KALEIDOSCOPE_LAUNCH'
HEADER_REQUEST_ID = 'X-Kaleidoscope-Request-Id'
HEADER_SERVER_TIMING = 'Server-Timing'
INJECTABLE_CONTENT_MAX = 10_485_760
SERVER_TIMING_DESCRIPTION_LENGTH_MAX = 200
SERVER_TIMING_NAME_LENGTH_MAX = 64
TEMPLATE_DIR = Path(__file__).parent / 'templates'
_BODY_CLOSE_PATTERN = re.compile(r'</body\s*>', re.IGNORECASE)
_CONTROL_CHARACTER_PATTERN = re.compile(r'[\x00-\x1f\x7f]')
_CSP_NONCE_ATTRIBUTES = ('_csp_nonce', 'csp_nonce')
_HOST_OPENING = '<div id="ks-app"'
_HTML_TYPES = frozenset({'text/html', 'application/xhtml+xml'})
_INJECTABLE_STATUSES = frozenset(range(200, 300)) - {204, 205, 206}
_SCRIPT_OPENING = '<script '
_SCRIPT_PATH = KALEIDOSCOPE_URL_PREFIX + 'static/kaleidoscope.js'
_TOKEN_UNSAFE_PATTERN = re.compile(r"[^!#$%&'*+\-.^_`|~0-9A-Za-z]")

logger = logging.getLogger(__name__)


def _body_close_index(content: str) -> int | None:
    index = None

    for match in _BODY_CLOSE_PATTERN.finditer(content):
        index = match.start()

    return index


def _csp_nonce(request: HttpRequest) -> str | None:
    for attribute in _CSP_NONCE_ATTRIBUTES:
        nonce = getattr(request, attribute, None)

        if nonce:
            return str(nonce)

    return None


def _is_injectable(response: HttpResponse) -> bool:
    if not is_html_response(response):
        return False

    if response.status_code not in _INJECTABLE_STATUSES:
        return False

    if response.get('Content-Encoding', ''):
        return False

    return len(response.content) <= INJECTABLE_CONTENT_MAX


def _server_timing_entries(context: KaleidoscopeContext) -> list[str]:
    entries = []

    for panel in context.panels:
        if not isinstance(panel, Panel):
            message = f'the context holds a {type(panel).__name__} among its panels'
            raise TypeError(message)

        try:
            panel_entries = _server_timing_panel_entries(panel, context)
        except Exception:
            logger.exception('Kaleidoscope panel %r failed to report timing', panel.panel_id)
            continue

        entries.extend(panel_entries)

    return entries


def _server_timing_panel_entries(panel: Panel, context: KaleidoscopeContext) -> list[str]:
    entries = []

    for metric in panel.get_server_timing(context):
        if not isinstance(metric, ServerTimingMetric):
            message = (
                f'the {panel.panel_id} panel reported a {type(metric).__name__} '
                f'instead of a ServerTimingMetric'
            )

            raise TypeError(message)

        entry = server_timing_entry(
            f'{panel.panel_id}_{metric.key}',
            metric.duration,
            metric.description,
        )

        if entry is not None:
            entries.append(entry)

    return entries


def is_html_response(response: HttpResponse) -> bool:
    if not isinstance(response, HttpResponseBase):
        message = f'response must be an HttpResponseBase: {type(response).__name__}'
        raise TypeError(message)

    if getattr(response, 'streaming', False):
        return False

    content_type = response.get('Content-Type', '').split(';')[0].strip().lower()

    return content_type in _HTML_TYPES


def launch_token() -> str:
    return os.environ.setdefault(ENVIRONMENT_LAUNCH, uuid.uuid4().hex)


def server_timing_entry(name: str, duration: float, description: str) -> str | None:
    if not isinstance(name, str):
        message = f'name must be text: {name!r}'
        raise TypeError(message)

    if isinstance(duration, bool):
        message = f'duration must be a number, not a bool: {duration!r}'
        raise TypeError(message)

    if not isinstance(duration, (int, float)):
        message = f'duration must be a number: {duration!r}'
        raise TypeError(message)

    if not isinstance(description, str):
        message = f'description must be text: {description!r}'
        raise TypeError(message)

    token = _TOKEN_UNSAFE_PATTERN.sub('_', name)[:SERVER_TIMING_NAME_LENGTH_MAX]

    if not token:
        return None

    if not math.isfinite(duration):
        return None

    text = _CONTROL_CHARACTER_PATTERN.sub(' ', description)[:SERVER_TIMING_DESCRIPTION_LENGTH_MAX]
    text_ascii = text.encode('ascii', errors='replace').decode('ascii')
    quoted = text_ascii.replace('\\', '\\\\').replace('"', '\\"')
    entry = f'{token};dur={duration:.2f};desc="{quoted}"'

    if not entry.isascii():
        message = f'a server timing entry must be ascii: {entry!r}'
        raise RuntimeError(message)

    if _CONTROL_CHARACTER_PATTERN.search(entry):
        message = f'a server timing entry must not carry control characters: {entry!r}'
        raise RuntimeError(message)

    return entry


class ResponseInjector:
    def __init__(self) -> None:
        template_path = TEMPLATE_DIR / 'shell.html'
        template = template_path.read_text(encoding='utf-8')

        if _SCRIPT_PATH not in template:
            message = f'the shell at {template_path} never loads {_SCRIPT_PATH}'
            raise RuntimeError(message)

        if _SCRIPT_OPENING not in template:
            message = f'the shell at {template_path} has no {_SCRIPT_OPENING!r} for the CSP nonce'
            raise RuntimeError(message)

        if _HOST_OPENING not in template:
            message = f'the shell at {template_path} has no {_HOST_OPENING!r} for the launch token'
            raise RuntimeError(message)

        host = f'{_HOST_OPENING} data-launch="{escape(launch_token())}"'
        self._shell_template = template.replace(_HOST_OPENING, host)

    def _inject(self, request: HttpRequest, response: HttpResponse) -> None:
        if not _is_injectable(response):
            return

        try:
            content = response.content.decode(response.charset)
        except (LookupError, UnicodeError):
            return

        if _SCRIPT_PATH in content:
            return

        index = _body_close_index(content)

        if index is None:
            return

        shell = self._shell_build(request)
        content_injected = content[:index] + shell + content[index:]

        try:
            encoded = content_injected.encode(response.charset)
        except (LookupError, UnicodeError):
            return

        response.content = encoded
        response['Content-Length'] = len(encoded)

    def _server_timing_add(self, response: HttpResponse, context: KaleidoscopeContext) -> None:
        entries = _server_timing_entries(context)

        if not entries:
            return

        header = ', '.join(entries)
        existing = response.get(HEADER_SERVER_TIMING, '')

        if existing:
            header = f'{existing}, {header}'

        response[HEADER_SERVER_TIMING] = header

    def _shell_build(self, request: HttpRequest) -> str:
        nonce = _csp_nonce(request)

        if nonce is None:
            return self._shell_template

        return self._shell_template.replace(_SCRIPT_OPENING, f'<script nonce="{escape(nonce)}" ')

    def process(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> HttpResponse:
        if not isinstance(request, HttpRequest):
            message = f'request must be an HttpRequest: {type(request).__name__}'
            raise TypeError(message)

        if not isinstance(response, HttpResponseBase):
            message = f'response must be an HttpResponseBase: {type(response).__name__}'
            raise TypeError(message)

        if not isinstance(context, KaleidoscopeContext):
            message = f'context must be a KaleidoscopeContext: {type(context).__name__}'
            raise TypeError(message)

        self._server_timing_add(response, context)
        response[HEADER_REQUEST_ID] = context.request_id

        if context.is_ajax:
            return response

        self._inject(request, response)

        return response
