from __future__ import annotations

import inspect

from typing import TYPE_CHECKING, get_type_hints

from django.conf import settings
from django.utils.module_loading import import_string

from kaleidoscope.constants import PANELS_MAX

if TYPE_CHECKING:
    from kaleidoscope.container import ServiceContainer
    from kaleidoscope.panel import Panel


DEFAULT_PANELS = [
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
]


class PanelRegistry:
    def __init__(self, container: ServiceContainer) -> None:
        self._container = container
        self._panels: dict[str, Panel] = {}
        self._load()

    def _create_panel(self, cls: type[Panel]) -> Panel:
        try:
            hints = get_type_hints(cls.__init__)
        except Exception as exception:
            message = f'Failed to resolve type hints for {cls.__name__}: {exception}'
            raise TypeError(message) from exception

        signature = inspect.signature(cls.__init__)
        kwargs = {}

        for param_name in signature.parameters:
            if param_name == 'self':
                continue

            hint = hints.get(param_name)

            if hint and self._container.has(hint):
                kwargs[param_name] = self._container.get(hint)

        return cls(**kwargs)

    def _load(self) -> None:
        from kaleidoscope.panel import Installable  # noqa: PLC0415

        panel_paths = getattr(settings, 'KALEIDOSCOPE_PANELS', DEFAULT_PANELS)

        for path in panel_paths[:PANELS_MAX]:
            cls = import_string(path)

            panel = self._create_panel(cls)

            if isinstance(panel, Installable):
                panel.install()

            self._panels[panel.panel_id] = panel

    @property
    def panels(self) -> dict[str, Panel]:
        return self._panels

    def get(self, panel_id: str) -> Panel | None:
        return self._panels.get(panel_id)

    def teardown(self) -> None:
        from kaleidoscope.panel import Installable  # noqa: PLC0415

        for panel in self._panels.values():
            if isinstance(panel, Installable):
                panel.uninstall()

        self._panels.clear()
