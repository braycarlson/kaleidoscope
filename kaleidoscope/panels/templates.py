from __future__ import annotations

import functools
import json
import threading
import time

from contextvars import ContextVar
from typing import TYPE_CHECKING

from django.http import JsonResponse
from django.template import Template

from kaleidoscope.constants import (
    CONTEXT_DICTS_MAX,
    CONTEXT_KEYS_MAX,
    TEMPLATES_PER_REQUEST_MAX,
)
from kaleidoscope.panel import Installable, Panel, RequestHook, ResponseHook
from kaleidoscope.serializer import Serializer

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext


_collecting: ContextVar[list | None] = ContextVar('_template_collecting', default=None)


class TemplatesPanel(Panel, Installable, RequestHook, ResponseHook):
    panel_id = 'templates'
    title = 'Templates'

    _original_render = Template.render

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}
        self._context_raw: list[dict] = []
        self._lock = threading.Lock()
        self._serializer = Serializer()

    def _collect_context(self, context: object) -> tuple[dict, list[str]]:
        items: dict[str, object] = {}

        if hasattr(context, 'dicts'):
            try:
                dict_list = list(context.dicts)[:CONTEXT_DICTS_MAX]  # ty:ignore[not-iterable]
            except Exception:
                dict_list = []
        elif isinstance(context, dict):
            dict_list = [context]
        else:
            dict_list = []

        for dict_entry in dict_list:
            if not isinstance(dict_entry, dict):
                continue

            for key, value in dict_entry.items():
                if not isinstance(key, str):
                    continue

                if key.startswith('_'):
                    continue

                if key in ('True', 'False', 'None'):
                    continue

                items[key] = value

                if len(items) >= CONTEXT_KEYS_MAX:
                    break

            if len(items) >= CONTEXT_KEYS_MAX:
                break

        return items, sorted(items.keys())

    def install(self) -> None:
        panel = self
        original = TemplatesPanel._original_render

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
                try:
                    merged, keys = panel._collect_context(context)
                except Exception:
                    merged, keys = {}, []

                templates.append({
                    'context_keys': keys,
                    'duration_ms': round(duration, 2),
                    'name': name,
                    '_merged': merged,
                })

            return result

        Template.render = patched_render  # ty:ignore[invalid-assignment]

    def uninstall(self) -> None:
        Template.render = TemplatesPanel._original_render

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

    def handle_action(self, action: str, request: HttpRequest) -> HttpResponse | None:
        if action == 'value':
            try:
                template_index = int(request.GET.get('template', '-1'))
                steps = json.loads(request.GET.get('path', '[]'))
            except (ValueError, TypeError):
                return JsonResponse({'error': 'invalid params'}, status=400)

            if not isinstance(steps, list):
                return JsonResponse({'error': 'invalid path'}, status=400)

            with self._lock:
                if template_index < 0 or template_index >= len(self._context_raw):
                    return JsonResponse({'error': 'template not found'}, status=404)

                context_raw = self._context_raw[template_index]

            try:
                value = self._serializer.resolve_path(context_raw, steps)
            except Exception as exception:
                return JsonResponse({'error': str(exception)}, status=400)

            return JsonResponse({'value': self._serializer.serialize(value)})

        return None

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

        templates_raw = _collecting.get(None) or []
        _collecting.set(None)

        if context.is_ajax:
            return

        total_time = sum(template['duration_ms'] for template in templates_raw)

        templates_public = []
        context_raw_list = []

        for template in templates_raw:
            merged = template.pop('_merged', {})
            templates_public.append(template)
            context_raw_list.append(merged)

        with self._lock:
            self._data = {
                'count': len(templates_public),
                'templates': templates_public,
                'total_time': round(total_time, 2),
            }
            self._context_raw = context_raw_list
