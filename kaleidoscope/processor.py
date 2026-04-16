from __future__ import annotations

from typing import TYPE_CHECKING

from kaleidoscope.panel import (
    AsyncRequestHook,
    AsyncResponseHook,
    Panel,
    RequestHook,
    ResponseHook,
)

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext
    from kaleidoscope.registry import PanelRegistry


class RequestProcessor:
    def __init__(self, registry: PanelRegistry) -> None:
        self._registry = registry

    def _active_panels(self) -> list[Panel]:
        panels = list(self._registry.panels.values())
        isolated = [panel for panel in panels if panel.enabled and panel.isolate]

        if isolated:
            return isolated

        return [panel for panel in panels if panel.enabled]

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        active = self._active_panels()

        for panel in active:
            if isinstance(panel, RequestHook):
                panel.process_request(request, context)

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        active = self._active_panels()

        for panel in reversed(active):
            if isinstance(panel, ResponseHook):
                panel.process_response(request, response, context)

    async def aprocess_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        active = self._active_panels()

        for panel in active:
            if isinstance(panel, AsyncRequestHook):
                await panel.aprocess_request(request, context)
                continue

            if isinstance(panel, RequestHook):
                panel.process_request(request, context)

    async def aprocess_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        active = self._active_panels()

        for panel in reversed(active):
            if isinstance(panel, AsyncResponseHook):
                await panel.aprocess_response(request, response, context)
                continue

            if isinstance(panel, ResponseHook):
                panel.process_response(request, response, context)
