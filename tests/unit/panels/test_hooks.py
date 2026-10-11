from __future__ import annotations

import pytest

from typing import TYPE_CHECKING

from django.http import HttpResponse

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panels.cache import CachePanel
from kaleidoscope.panels.line_profiling import LineProfilingPanel
from kaleidoscope.panels.memory import MemoryPanel
from kaleidoscope.panels.profiling import ProfilingPanel
from kaleidoscope.panels.queries import QueriesPanel
from kaleidoscope.panels.request import RequestPanel
from kaleidoscope.panels.static_files import StaticFilesPanel
from kaleidoscope.panels.templates import TemplatesPanel
from kaleidoscope.panels.timer import TimerPanel

if TYPE_CHECKING:
    from django.test import RequestFactory

    from kaleidoscope.panel import Panel, RequestHook, ResponseHook


PANELS_ACTION = (ProfilingPanel, QueriesPanel, TemplatesPanel)
PANELS_REQUEST_CONTEXT = (LineProfilingPanel, MemoryPanel, ProfilingPanel, QueriesPanel)
PANELS_RESPONSE_REQUEST = (QueriesPanel, RequestPanel, TimerPanel)
PANELS_RESPONSE_RESPONSE = (QueriesPanel, RequestPanel, StaticFilesPanel, TimerPanel)
PANELS_SERVER_TIMING = (QueriesPanel, TimerPanel)

PANELS_RESPONSE_CONTEXT = (
    CachePanel,
    LineProfilingPanel,
    MemoryPanel,
    ProfilingPanel,
    QueriesPanel,
    RequestPanel,
    StaticFilesPanel,
    TemplatesPanel,
    TimerPanel,
)


@pytest.mark.parametrize('panel_class', PANELS_REQUEST_CONTEXT)
def test_a_request_hook_refuses_a_context_of_the_wrong_kind(
    panel_class: type[RequestHook],
    request_factory: RequestFactory,
) -> None:
    panel = panel_class()
    request = request_factory.get('/')
    context: dict = {}

    with pytest.raises(TypeError, match='needs a KaleidoscopeContext, not dict'):
        panel.process_request(request, context)  # ty:ignore[invalid-argument-type]


@pytest.mark.parametrize('panel_class', PANELS_RESPONSE_CONTEXT)
def test_a_response_hook_refuses_a_context_of_the_wrong_kind(
    panel_class: type[ResponseHook],
    request_factory: RequestFactory,
) -> None:
    panel = panel_class()
    request = request_factory.get('/')
    response = HttpResponse()
    context: dict = {}

    with pytest.raises(TypeError, match='needs a KaleidoscopeContext, not dict'):
        panel.process_response(request, response, context)  # ty:ignore[invalid-argument-type]


@pytest.mark.parametrize('panel_class', PANELS_RESPONSE_REQUEST)
def test_a_response_hook_refuses_a_request_of_the_wrong_kind(
    panel_class: type[ResponseHook],
) -> None:
    panel = panel_class()
    response = HttpResponse()
    context = KaleidoscopeContext()

    with pytest.raises(TypeError, match='needs an HttpRequest, not NoneType'):
        panel.process_response(None, response, context)  # ty:ignore[invalid-argument-type]


@pytest.mark.parametrize('panel_class', PANELS_RESPONSE_RESPONSE)
def test_a_response_hook_refuses_a_response_of_the_wrong_kind(
    panel_class: type[ResponseHook],
    request_factory: RequestFactory,
) -> None:
    panel = panel_class()
    request = request_factory.get('/')
    context = KaleidoscopeContext()

    with pytest.raises(TypeError, match='needs an HttpResponse, not str'):
        panel.process_response(request, 'done', context)  # ty:ignore[invalid-argument-type]


@pytest.mark.parametrize('panel_class', PANELS_ACTION)
def test_a_panel_refuses_an_action_that_is_not_text(
    panel_class: type[Panel],
    request_factory: RequestFactory,
) -> None:
    panel = panel_class()
    request = request_factory.get('/')

    with pytest.raises(TypeError, match='action must be text: 7'):
        panel.handle_action(7, request)  # ty:ignore[invalid-argument-type]


@pytest.mark.parametrize('panel_class', PANELS_SERVER_TIMING)
def test_server_timing_refuses_a_context_of_the_wrong_kind(panel_class: type[Panel]) -> None:
    panel = panel_class()
    context: dict = {}

    with pytest.raises(TypeError, match='needs a KaleidoscopeContext, not dict'):
        panel.get_server_timing(context)  # ty:ignore[invalid-argument-type]
