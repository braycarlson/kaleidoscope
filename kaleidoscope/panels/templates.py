from __future__ import annotations

import functools
import json
import time

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.http import HttpRequest, JsonResponse
from django.template import Context, Template

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Installable, Panel, RequestHook, ResponseHook
from kaleidoscope.patch import is_patched, method_patch, method_unpatch, patch_marked
from kaleidoscope.serializer import resolve_path, serialize

if TYPE_CHECKING:
    from typing import Callable

    from django.http import HttpResponse


CONTEXT_DICTS_MAX = 256
CONTEXT_KEYS_MAX = 1_024
TEMPLATE_NAME_INLINE = '<inline>'
TEMPLATE_VALUE_PATH_LENGTH_MAX = 8_192
TEMPLATE_VALUE_STEPS_MAX = 64
TEMPLATES_PER_REQUEST_MAX = 2_048
_KEYS_RESERVED = frozenset({'True', 'False', 'None'})
_collecting: ContextVar[list[TemplateRender] | None] = ContextVar(
    '_template_collecting',
    default=None,
)

_depth: ContextVar[int] = ContextVar('_template_depth', default=0)


@dataclass(slots=True)
class TemplateRender:
    context: dict[str, object]
    depth: int
    duration_ms: float
    name: str

    def listed(self) -> dict:
        return {
            'context_keys': sorted(self.context),
            'duration_ms': self.duration_ms,
            'name': self.name,
        }


def _context_dicts(context: object) -> list:
    if isinstance(context, Context):
        return list(context.dicts)[:CONTEXT_DICTS_MAX]

    if isinstance(context, dict):
        return [context]

    return []


def _context_items(context: object) -> dict[str, object]:
    items: dict[str, object] = {}

    for entry in _context_dicts(context):
        if not isinstance(entry, dict):
            continue

        for key, value in entry.items():
            if len(items) >= CONTEXT_KEYS_MAX:
                return items

            if not isinstance(key, str):
                continue

            if key.startswith('_'):
                continue

            if key in _KEYS_RESERVED:
                continue

            items[key] = value

    return items


def _render_timed(
    original: Callable,
    template: Template,
    context: Context,
    *,
    renders: list[TemplateRender],
) -> str:
    try:
        items = _context_items(context)
    except Exception:
        items = {}

    name = getattr(template, 'name', None) or TEMPLATE_NAME_INLINE
    render = TemplateRender(context=items, depth=_depth.get(), duration_ms=0.0, name=name)

    renders.append(render)
    token = _depth.set(render.depth + 1)
    started_ns = time.perf_counter_ns()

    try:
        result = original(template, context)
    finally:
        render.duration_ms = round((time.perf_counter_ns() - started_ns) / 1_000_000, 2)

        _depth.reset(token)

    return result


def _render_wrapper_build(original: Callable) -> Callable:
    if not callable(original):
        message = f'original must be callable, not {type(original).__name__}'
        raise TypeError(message)

    if is_patched(original):
        message = 'Template._render is already wrapped by kaleidoscope'
        raise RuntimeError(message)

    @functools.wraps(original)
    def render_tracked(template: Template, context: Context) -> str:
        renders = _collecting.get(None)

        if renders is None:
            return original(template, context)

        if len(renders) >= TEMPLATES_PER_REQUEST_MAX:
            return original(template, context)

        return _render_timed(original, template, context, renders=renders)

    return patch_marked(render_tracked)


def _value_steps(request: HttpRequest) -> list | None:
    try:
        steps = json.loads(request.GET.get('path', '[]'))
    except (RecursionError, TypeError, ValueError):
        return None

    if not isinstance(steps, list):
        return None

    return steps


class TemplatesPanel(Panel, Installable, RequestHook, ResponseHook):
    panel_id = 'templates'
    title = 'Templates'

    def __init__(self) -> None:
        super().__init__()

        self._contexts: list[dict] = []
        self._data: dict = {}

    def _value_respond(self, request: HttpRequest) -> HttpResponse:
        if not isinstance(request, HttpRequest):
            message = f'{self.title} needs an HttpRequest, not {type(request).__name__}'
            raise TypeError(message)

        if len(request.GET.get('path', '')) > TEMPLATE_VALUE_PATH_LENGTH_MAX:
            return JsonResponse({'error': 'path too long'}, status=400)

        steps = _value_steps(request)

        if steps is None:
            return JsonResponse({'error': 'invalid params'}, status=400)

        if len(steps) > TEMPLATE_VALUE_STEPS_MAX:
            return JsonResponse({'error': 'path too deep'}, status=400)

        try:
            template_index = int(request.GET.get('template', '-1'))
        except ValueError:
            return JsonResponse({'error': 'invalid params'}, status=400)

        contexts = self._contexts

        if template_index < 0:
            return JsonResponse({'error': 'template not found'}, status=404)

        if template_index >= len(contexts):
            return JsonResponse({'error': 'template not found'}, status=404)

        try:
            value = resolve_path(contexts[template_index], steps)
        except Exception as exception:
            return JsonResponse({'error': str(exception)}, status=400)

        return JsonResponse({'value': serialize(value)})

    def get_data(self) -> dict:
        return dict(self._data)

    def get_summary(self) -> str:
        data = self._data
        count = data.get('count', 0)

        if count:
            return f'{count} templates, {data.get("total_time", 0)} ms'

        return ''

    def handle_action(self, action: str, request: HttpRequest) -> HttpResponse | None:
        if not isinstance(action, str):
            message = f'action must be text: {action!r}'
            raise TypeError(message)

        if action != 'value':
            return None

        return self._value_respond(request)

    def install(self) -> None:
        method_patch(Template, '_render', _render_wrapper_build)

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

        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        renders = _collecting.get(None) or []

        _collecting.set(None)

        if len(renders) > TEMPLATES_PER_REQUEST_MAX:
            message = f'{self.title} holds {len(renders)} renders, over {TEMPLATES_PER_REQUEST_MAX}'
            raise RuntimeError(message)

        if context.is_ajax:
            return

        self._contexts = [render.context for render in renders]
        durations_outermost = [render.duration_ms for render in renders if render.depth == 0]

        self._data = {
            'count': len(renders),
            'templates': [render.listed() for render in renders],
            'total_time': round(sum(durations_outermost), 2),
        }

    def uninstall(self) -> None:
        method_unpatch(Template, '_render')
