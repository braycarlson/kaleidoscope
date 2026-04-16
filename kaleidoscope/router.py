from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from django.http import HttpResponse, HttpResponseNotFound, JsonResponse

from kaleidoscope.constants import KALEIDOSCOPE_URL_PREFIX

if TYPE_CHECKING:
    from django.http import HttpRequest

    from kaleidoscope.panel import Panel
    from kaleidoscope.registry import PanelRegistry


STATIC_DIR = Path(__file__).parent / 'static' / 'kaleidoscope'

_STATIC_DIR_RESOLVED = STATIC_DIR.resolve()


def _set_enabled(panel: Panel, value: bool) -> JsonResponse:
    panel.enabled = value

    return JsonResponse({'enabled': value})


_PANEL_ACTIONS = {
    'data': lambda panel, _request: JsonResponse(panel.get_data()),
    'enable': lambda panel, _request: _set_enabled(panel, value=True),
    'disable': lambda panel, _request: _set_enabled(panel, value=False),
}


class Router:
    def __init__(self, registry: PanelRegistry) -> None:
        self._registry = registry

    def dispatch(self, request: HttpRequest, is_authorized: bool) -> HttpResponse:
        if not is_authorized:
            return HttpResponseNotFound()

        if hasattr(request, 'session'):
            request.session.modified = False  # ty:ignore[unresolved-attribute]

        prefix_length = len(KALEIDOSCOPE_URL_PREFIX)
        path = request.path[prefix_length:]

        if path == 'panels/':
            return self._list_panels()

        if path.startswith('panels/'):
            return self._handle_panel(path, request)

        if path.startswith('static/'):
            return self._serve_static(path[len('static/'):])

        return HttpResponseNotFound()

    def _list_panels(self) -> JsonResponse:
        panels = list(self._registry.panels.values())

        return JsonResponse({
            'panels': [
                {**panel.get_metadata(), 'enabled': panel.enabled}
                for panel in panels
            ]
        })

    def _handle_panel(self, path: str, request: HttpRequest) -> HttpResponse:
        parts = path.strip('/').split('/')

        if len(parts) < 2:
            return HttpResponseNotFound()

        panel_id = parts[1]

        panel = self._registry.get(panel_id)

        if not panel:
            return HttpResponseNotFound()

        if len(parts) == 3:
            action_name = parts[2]
            handler = _PANEL_ACTIONS.get(action_name)

            if handler:
                return handler(panel, request)

        if len(parts) >= 3 and parts[2] == 'action':
            action = '/'.join(parts[3:])
            result = panel.handle_action(action, request)

            if result:
                return result

        return HttpResponseNotFound()

    def _serve_static(self, filename: str) -> HttpResponse:
        if '..' in filename:
            return HttpResponseNotFound()

        filepath = (STATIC_DIR / filename).resolve()

        if not filepath.is_relative_to(_STATIC_DIR_RESOLVED):
            return HttpResponseNotFound()

        if not filepath.is_file():
            return HttpResponseNotFound()

        content_types = {
            '.css': 'text/css',
            '.js': 'application/javascript',
        }

        content_type = content_types.get(filepath.suffix, 'application/octet-stream')
        content = filepath.read_text(encoding='utf-8')

        return HttpResponse(content, content_type=content_type)
