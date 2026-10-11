from __future__ import annotations

import logging
import threading

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponseBase
from django.utils.module_loading import import_string

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Installable, Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpResponse


DEFAULT_PANELS = (
    'kaleidoscope.panels.timer.TimerPanel',
    'kaleidoscope.panels.versions.VersionsPanel',
    'kaleidoscope.panels.request.RequestPanel',
    'kaleidoscope.panels.queries.QueriesPanel',
    'kaleidoscope.panels.templates.TemplatesPanel',
    'kaleidoscope.panels.cache.CachePanel',
    'kaleidoscope.panels.static_files.StaticFilesPanel',
    'kaleidoscope.panels.signals.SignalsPanel',
    'kaleidoscope.panels.settings.SettingsPanel',
    'kaleidoscope.panels.memory.MemoryPanel',
    'kaleidoscope.panels.profiling.ProfilingPanel',
    'kaleidoscope.panels.line_profiling.LineProfilingPanel',
)

PANELS_MAX = 64

logger = logging.getLogger(__name__)


def _panel_built(path: str) -> Panel:
    cls = import_string(path)

    if not isinstance(cls, type):
        message = f'KALEIDOSCOPE_PANELS entry {path!r} is not a class'
        raise ImproperlyConfigured(message)

    if not issubclass(cls, Panel):
        message = f'KALEIDOSCOPE_PANELS entry {path!r} is not a subclass of Panel'
        raise ImproperlyConfigured(message)

    return cls()


def _panels_keyed(panels: list[Panel]) -> dict[str, Panel]:
    keyed: dict[str, Panel] = {}

    for panel in panels:
        if not isinstance(panel, Panel):
            message = f'a registry holds Panel instances, not {type(panel).__name__}'
            raise TypeError(message)

        if not isinstance(panel.panel_id, str):
            message = f'{type(panel).__name__}.panel_id must be text: {panel.panel_id!r}'
            raise TypeError(message)

        if not panel.panel_id:
            message = f'{type(panel).__name__}.panel_id must not be empty'
            raise ValueError(message)

        if panel.panel_id in keyed:
            message = f'the panel_id {panel.panel_id!r} is registered twice'
            raise ValueError(message)

        keyed[panel.panel_id] = panel

    return keyed


def panels_load() -> list[Panel]:
    paths = getattr(settings, 'KALEIDOSCOPE_PANELS', DEFAULT_PANELS)

    if not isinstance(paths, (list, tuple)):
        message = f'KALEIDOSCOPE_PANELS must be a list or tuple, not {type(paths).__name__}'
        raise ImproperlyConfigured(message)

    if len(paths) > PANELS_MAX:
        message = f'KALEIDOSCOPE_PANELS names {len(paths)} panels, over the limit of {PANELS_MAX}'
        raise ImproperlyConfigured(message)

    return [_panel_built(path) for path in paths]


class PanelRegistry:
    def __init__(self, panels: list[Panel]) -> None:
        if len(panels) > PANELS_MAX:
            message = f'a registry holds at most {PANELS_MAX} panels, not {len(panels)}'
            raise ValueError(message)

        self._lock = threading.Lock()
        self._panels = _panels_keyed(panels)

        self._isolated_normalize()
        self._installed_sync()

    def _active(self) -> list[Panel]:
        enabled = [panel for panel in self._panels.values() if panel.enabled]
        isolated = [panel for panel in enabled if panel.isolate]

        if len(isolated) > 1:
            identifiers = [panel.panel_id for panel in isolated]
            message = f'only one isolated panel may be enabled at a time: {identifiers!r}'
            raise RuntimeError(message)

        if isolated:
            return isolated

        return enabled

    def _hook_arguments_validate(self, request: object, context: object) -> None:
        if not isinstance(request, HttpRequest):
            message = f'request must be an HttpRequest: {type(request).__name__}'
            raise TypeError(message)

        if not isinstance(context, KaleidoscopeContext):
            message = f'context must be a KaleidoscopeContext: {type(context).__name__}'
            raise TypeError(message)

    def _installed_sync(self) -> None:
        active = self._active()

        for panel in self._panels.values():
            if not isinstance(panel, Installable):
                continue

            if panel in active:
                panel.install()
            else:
                panel.uninstall()

    def _isolated_disable(self) -> None:
        for panel in self._panels.values():
            if panel.isolate:
                panel.enabled = False

    def _isolated_normalize(self) -> None:
        enabled = [panel for panel in self._panels.values() if panel.enabled]
        isolated = [panel for panel in enabled if panel.isolate]

        for panel in isolated[1:]:
            panel.enabled = False

    def _registered_validate(self, panels: list[Panel]) -> None:
        for panel in panels:
            if self._panels.get(panel.panel_id) is not panel:
                message = f'the panel {panel.panel_id!r} is not registered'
                raise ValueError(message)

    @property
    def panels(self) -> dict[str, Panel]:
        return self._panels

    def active(self) -> list[Panel]:
        with self._lock:
            return self._active()

    def enabled_set(self, panel: Panel, *, enabled: bool) -> None:
        if not isinstance(enabled, bool):
            message = f'enabled must be a bool: {enabled!r}'
            raise TypeError(message)

        self._registered_validate([panel])

        with self._lock:
            if enabled:
                if panel.isolate:
                    self._isolated_disable()

            panel.enabled = enabled

            self._installed_sync()

    def get(self, panel_id: str) -> Panel | None:
        if not isinstance(panel_id, str):
            message = f'panel_id must be text: {panel_id!r}'
            raise TypeError(message)

        panel = self._panels.get(panel_id)

        if panel is not None:
            if panel.panel_id != panel_id:
                message = f'the panel under {panel_id!r} now reports {panel.panel_id!r}'
                raise RuntimeError(message)

        return panel

    def process_request(
        self,
        request: HttpRequest,
        context: KaleidoscopeContext,
        panels: list[Panel],
    ) -> None:
        self._hook_arguments_validate(request, context)
        self._registered_validate(panels)

        hooks = [panel for panel in panels if isinstance(panel, RequestHook)]

        for panel in hooks:
            try:
                panel.process_request(request, context)
            except Exception:
                logger.exception(
                    'Kaleidoscope panel %r failed to process a request',
                    panel.panel_id,
                )

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
        panels: list[Panel],
    ) -> None:
        if not isinstance(response, HttpResponseBase):
            message = f'response must be an HttpResponseBase: {type(response).__name__}'
            raise TypeError(message)

        self._hook_arguments_validate(request, context)
        self._registered_validate(panels)

        hooks = [panel for panel in reversed(panels) if isinstance(panel, ResponseHook)]

        for panel in hooks:
            try:
                panel.process_response(request, response, context)
            except Exception:
                logger.exception(
                    'Kaleidoscope panel %r failed to process a response',
                    panel.panel_id,
                )

    def teardown(self) -> None:
        with self._lock:
            for panel in self._panels.values():
                if isinstance(panel, Installable):
                    panel.uninstall()

            self._panels.clear()
