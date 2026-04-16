from __future__ import annotations

import functools
import threading
import time

from contextvars import ContextVar
from typing import TYPE_CHECKING

from django.template import Template

from kaleidoscope.constants import CONTEXT_DICTS_MAX, CONTEXT_KEYS_MAX, TEMPLATES_PER_REQUEST_MAX
from kaleidoscope.panel import Installable, Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext


_collecting: ContextVar[list | None] = ContextVar('_template_collecting', default=None)


class TemplatesPanel(Panel, Installable, RequestHook, ResponseHook):
    panel_id = 'templates'
    title = 'Templates'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}
        self._lock = threading.Lock()
        self._original_render = Template.render

    def _format_context(self, context: object) -> list[str]:
        keys: set[str] = set()

        if hasattr(context, 'dicts'):
            for dict_entry in list(context.dicts)[:CONTEXT_DICTS_MAX]:  # ty:ignore[not-iterable]
                if isinstance(dict_entry, dict):
                    keys.update(dict_entry.keys())

                if len(keys) >= CONTEXT_KEYS_MAX:
                    break
        else:
            if isinstance(context, dict):
                keys.update(list(context.keys())[:CONTEXT_KEYS_MAX])

        return sorted(key for key in keys if not key.startswith('_'))

    def install(self) -> None:
        panel = self
        original = self._original_render

        @functools.wraps(original)
        def patched_render(template_self: Template, context: object) -> str:
            templates = _collecting.get(None)

            if templates is None:
                return original(template_self, context)

            start = time.perf_counter_ns()
            result = original(template_self, context)
            duration = (time.perf_counter_ns() - start) / 1_000_000

            name = getattr(template_self, 'name', None) or '<inline>'

            if len(templates) < TEMPLATES_PER_REQUEST_MAX:
                templates.append({
                    'context_keys': panel._format_context(context),
                    'duration_ms': round(duration, 2),
                    'name': name,
                })

            return result

        Template.render = patched_render  # ty:ignore[invalid-assignment]

    def uninstall(self) -> None:
        Template.render = self._original_render

    def get_data(self) -> dict:
        with self._lock:
            return dict(self._data)

    def get_summary(self) -> str:
        with self._lock:
            count = self._data.get('count', 0)
            total_time = self._data.get('total_time', 0)

        if count:
            return f'{count} templates, {total_time} ms'

        return ''

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request
        _ = context

        _collecting.set([])

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        _ = request
        _ = response

        templates = _collecting.get(None) or []
        _collecting.set(None)

        if context.is_ajax:
            return

        total_time = sum(template['duration_ms'] for template in templates)

        with self._lock:
            self._data = {
                'count': len(templates),
                'templates': templates,
                'total_time': round(total_time, 2),
            }
