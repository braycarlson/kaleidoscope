from __future__ import annotations

import logging
import stat

from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseForbidden,
    HttpResponseNotFound,
    JsonResponse,
)
from django.utils.cache import get_conditional_response
from django.utils.http import http_date

from kaleidoscope.registry import PanelRegistry

if TYPE_CHECKING:
    from kaleidoscope.panel import Panel


KALEIDOSCOPE_URL_PREFIX = '/__kaleidoscope__/'
STATIC_DIR = Path(__file__).parent / 'static' / 'kaleidoscope'
URL_PARTS_MAX = 16
_CONTENT_TYPES = MappingProxyType({'.css': 'text/css', '.js': 'application/javascript'})
_FETCH_SITES_FOREIGN = frozenset({'cross-site', 'same-site'})
_JSON_STRICT = MappingProxyType({'allow_nan': False})
_STATIC_DIR_RESOLVED = STATIC_DIR.resolve()

logger = logging.getLogger(__name__)


def _panel_action(panel: Panel, action: str, request: HttpRequest) -> HttpResponse:
    try:
        response = panel.handle_action(action, request)
    except Exception:
        logger.exception('Kaleidoscope panel %r failed on action %r', panel.panel_id, action)
        payload = {'error': f'The {panel.panel_id} panel failed on {action!r}.'}
        response = JsonResponse(payload, status=500)

    if response is None:
        return HttpResponseNotFound()

    if not isinstance(response, HttpResponseBase):
        logger.error(
            'Kaleidoscope panel %r answered %r with a %s instead of a response',
            panel.panel_id,
            action,
            type(response).__name__,
        )

        payload = {'error': f'The {panel.panel_id} panel answered {action!r} without a response.'}

        return JsonResponse(payload, status=500)

    return response


def _panel_data(panel: Panel) -> HttpResponse:
    try:
        data = panel.get_data()
        response = JsonResponse(data, json_dumps_params=_JSON_STRICT)
    except Exception:
        logger.exception('Kaleidoscope panel %r failed to build its data', panel.panel_id)
        payload = {'error': f'The {panel.panel_id} panel failed to build its data.'}
        response = JsonResponse(payload, status=500)

    return response


def _panel_listed(panel: Panel) -> dict:
    try:
        summary = panel.get_summary()
    except Exception:
        logger.exception('Kaleidoscope panel %r failed to summarize itself', panel.panel_id)
        summary = ''

    if not isinstance(summary, str):
        logger.error(
            'Kaleidoscope panel %r summarized itself with a %s instead of text',
            panel.panel_id,
            type(summary).__name__,
        )

        summary = ''

    return {
        'enabled': panel.enabled,
        'id': panel.panel_id,
        'isolate': panel.isolate,
        'summary': summary,
        'title': panel.title,
    }


def _static_serve(request: HttpRequest, filename: str) -> HttpResponse:
    if '..' in filename:
        return HttpResponseNotFound()

    if '\x00' in filename:
        return HttpResponseNotFound()

    try:
        filepath = (STATIC_DIR / filename).resolve()
        status = filepath.stat()
    except (OSError, RuntimeError, ValueError):
        return HttpResponseNotFound()

    if not filepath.is_relative_to(_STATIC_DIR_RESOLVED):
        return HttpResponseNotFound()

    if not stat.S_ISREG(status.st_mode):
        return HttpResponseNotFound()

    etag = f'"{status.st_mtime_ns:x}-{status.st_size:x}"'
    content_type = _CONTENT_TYPES.get(filepath.suffix, 'application/octet-stream')
    response = HttpResponse(content_type=content_type)
    response['Cache-Control'] = 'no-cache'
    response['ETag'] = etag
    response['Last-Modified'] = http_date(status.st_mtime)

    conditional = get_conditional_response(
        request,
        etag=etag,
        last_modified=int(status.st_mtime),
        response=response,
    )

    if conditional is not response:
        return conditional

    response.content = filepath.read_bytes()

    return response


class Router:
    def __init__(self, registry: PanelRegistry) -> None:
        if not isinstance(registry, PanelRegistry):
            message = f'registry must be a PanelRegistry: {type(registry).__name__}'
            raise TypeError(message)

        self._registry = registry

    def _panel_dispatch(self, path: str, request: HttpRequest) -> HttpResponse:
        parts = path.strip('/').split('/', URL_PARTS_MAX)

        if len(parts) < 3:
            return HttpResponseNotFound()

        panel = self._registry.get(parts[1])

        if panel is None:
            return HttpResponseNotFound()

        endpoint = parts[2]

        if endpoint == 'action':
            return _panel_action(panel, '/'.join(parts[3:]), request)

        if len(parts) > 3:
            return HttpResponseNotFound()

        if endpoint == 'data':
            return _panel_data(panel)

        if endpoint == 'enable':
            return self._panel_enabled(panel, enabled=True)

        if endpoint == 'disable':
            return self._panel_enabled(panel, enabled=False)

        return HttpResponseNotFound()

    def _panel_enabled(self, panel: Panel, *, enabled: bool) -> HttpResponse:
        self._registry.enabled_set(panel, enabled=enabled)

        return JsonResponse({'enabled': enabled})

    def _panels_list(self) -> JsonResponse:
        panels = [_panel_listed(panel) for panel in self._registry.panels.values()]

        return JsonResponse({'panels': panels})

    def dispatch(self, request: HttpRequest, is_shown: bool) -> HttpResponse:
        if not isinstance(request, HttpRequest):
            message = f'request must be an HttpRequest: {type(request).__name__}'
            raise TypeError(message)

        if not isinstance(is_shown, bool):
            message = f'is_shown must be a bool: {is_shown!r}'
            raise TypeError(message)

        if not request.path.startswith(KALEIDOSCOPE_URL_PREFIX):
            message = f'the router only serves {KALEIDOSCOPE_URL_PREFIX}, not {request.path!r}'
            raise ValueError(message)

        if not is_shown:
            return HttpResponseNotFound()

        if request.headers.get('Sec-Fetch-Site') in _FETCH_SITES_FOREIGN:
            return HttpResponseForbidden()

        if hasattr(request, 'session'):
            request.session.modified = False  # ty:ignore[unresolved-attribute]

        path = request.path[len(KALEIDOSCOPE_URL_PREFIX):]

        if path == 'panels/':
            return self._panels_list()

        if path.startswith('panels/'):
            return self._panel_dispatch(path, request)

        if path.startswith('static/'):
            return _static_serve(request, path[len('static/'):])

        return HttpResponseNotFound()
