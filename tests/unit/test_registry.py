from __future__ import annotations

import pytest

from typing import TYPE_CHECKING

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.template import Template
from django.test import override_settings

from kaleidoscope import registry
from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Installable, Panel, RequestHook, ResponseHook
from kaleidoscope.panels.queries import QueriesPanel
from kaleidoscope.registry import DEFAULT_PANELS, PanelRegistry, panels_load
from kaleidoscope.store import QueryStore

from tests.toolbar import PANEL_IDS_DEFAULT

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.test import RequestFactory


class _Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []


class _PanelSync(Panel, RequestHook, ResponseHook):
    def __init__(self, panel_id: str, recorder: _Recorder, *, isolate: bool = False) -> None:
        super().__init__()

        self.isolate = isolate
        self.panel_id = panel_id
        self.recorder = recorder

    def get_data(self) -> dict:
        return {}

    def get_summary(self) -> str:
        return ''

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request
        _ = context

        self.recorder.events.append(f'{self.panel_id}:request')

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        _ = request
        _ = response
        _ = context

        self.recorder.events.append(f'{self.panel_id}:response')


class _PanelBroken(_PanelSync):
    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request
        _ = context
        message = 'request hook is broken'

        raise RuntimeError(message)

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        _ = request
        _ = response
        _ = context
        message = 'response hook is broken'

        raise RuntimeError(message)


def _cycle_run(panel_registry: PanelRegistry, request: HttpRequest) -> KaleidoscopeContext:
    panels = panel_registry.active()
    context = KaleidoscopeContext(panels=panels)
    response = HttpResponse()

    panel_registry.process_request(request, context, panels)
    panel_registry.process_response(request, response, context, panels)

    return context


def test_registry_loads_the_default_panels_in_order() -> None:
    panels = PanelRegistry(panels_load()).panels

    assert tuple(panels) == PANEL_IDS_DEFAULT
    assert len(DEFAULT_PANELS) == len(PANEL_IDS_DEFAULT)


def test_the_queries_panel_owns_its_store() -> None:
    panel = PanelRegistry(panels_load()).get('queries')

    assert isinstance(panel, QueriesPanel)
    assert isinstance(panel.store, QueryStore)


@override_settings(KALEIDOSCOPE_PANELS=['kaleidoscope.panels.timer.TimerPanel'])
def test_registry_loads_only_the_configured_panels() -> None:
    panels = PanelRegistry(panels_load()).panels

    assert tuple(panels) == ('timer',)


def test_registry_refuses_more_panels_than_the_maximum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, 'PANELS_MAX', 2)

    with pytest.raises(ImproperlyConfigured, match='over the limit of 2'):
        panels_load()


def test_registry_installs_and_tears_down_installable_panels() -> None:
    original = Template._render
    panel_registry = PanelRegistry(panels_load())

    assert Template._render.__wrapped__ is original

    panel_registry.teardown()

    assert Template._render is original
    assert panel_registry.panels == {}


def test_registry_answers_none_for_an_unknown_panel() -> None:
    assert PanelRegistry(panels_load()).get('missing') is None


def test_request_hooks_run_in_order_and_response_hooks_in_reverse(
    request_factory: RequestFactory,
) -> None:
    recorder = _Recorder()
    panels = [_PanelSync('first', recorder), _PanelSync('second', recorder)]

    _cycle_run(PanelRegistry(panels), request_factory.get('/'))

    assert recorder.events == [
        'first:request',
        'second:request',
        'second:response',
        'first:response',
    ]


def test_disabled_panels_are_skipped(request_factory: RequestFactory) -> None:
    recorder = _Recorder()
    disabled = _PanelSync('disabled', recorder)
    disabled.enabled = False
    panels = [_PanelSync('active', recorder), disabled]

    _cycle_run(PanelRegistry(panels), request_factory.get('/'))

    assert recorder.events == ['active:request', 'active:response']


def test_an_enabled_isolated_panel_suspends_every_other_panel(
    request_factory: RequestFactory,
) -> None:
    recorder = _Recorder()
    panels = [_PanelSync('normal', recorder), _PanelSync('isolated', recorder, isolate=True)]

    _cycle_run(PanelRegistry(panels), request_factory.get('/'))

    assert recorder.events == ['isolated:request', 'isolated:response']


def test_the_panel_set_is_fixed_for_the_whole_request(request_factory: RequestFactory) -> None:
    recorder = _Recorder()
    first = _PanelSync('first', recorder)
    second = _PanelSync('second', recorder)
    panel_registry = PanelRegistry([first, second])
    request = request_factory.get('/')
    panels = panel_registry.active()
    context = KaleidoscopeContext(panels=panels)
    response = HttpResponse()

    panel_registry.process_request(request, context, panels)
    second.enabled = False

    panel_registry.process_response(request, response, context, panels)

    assert recorder.events == [
        'first:request',
        'second:request',
        'second:response',
        'first:response',
    ]


def test_a_raising_hook_is_logged_and_the_others_still_run(
    request_factory: RequestFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    recorder = _Recorder()

    panels = [
        _PanelSync('before', recorder),
        _PanelBroken('broken', recorder),
        _PanelSync('after', recorder),
    ]

    _cycle_run(PanelRegistry(panels), request_factory.get('/'))

    assert recorder.events == [
        'before:request',
        'after:request',
        'after:response',
        'before:response',
    ]

    assert "'broken' failed to process a request" in caplog.text
    assert "'broken' failed to process a response" in caplog.text


class _PanelInstallable(_PanelSync, Installable):
    def install(self) -> None:
        self.recorder.events.append(f'{self.panel_id}:install')

    def uninstall(self) -> None:
        self.recorder.events.append(f'{self.panel_id}:uninstall')


def test_registry_refuses_an_object_that_is_not_a_panel() -> None:
    with pytest.raises(TypeError, match='not object'):
        PanelRegistry([object()])  # ty:ignore[invalid-argument-type]


def test_registry_refuses_a_panel_without_an_identifier() -> None:
    with pytest.raises(ValueError, match='must not be empty'):
        PanelRegistry([_PanelSync('', _Recorder())])


def test_registry_refuses_a_panel_identifier_that_is_not_text() -> None:
    panel = _PanelSync('numbered', _Recorder())
    panel.panel_id = 7  # ty:ignore[invalid-assignment]

    with pytest.raises(TypeError, match='must be text'):
        PanelRegistry([panel])


def test_registry_refuses_a_panel_identifier_registered_twice() -> None:
    recorder = _Recorder()

    with pytest.raises(ValueError, match="'twice' is registered twice"):
        PanelRegistry([_PanelSync('twice', recorder), _PanelSync('twice', recorder)])


def test_registry_refuses_more_panels_than_it_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, 'PANELS_MAX', 1)
    recorder = _Recorder()

    with pytest.raises(ValueError, match='at most 1 panels'):
        PanelRegistry([_PanelSync('first', recorder), _PanelSync('second', recorder)])


@override_settings(KALEIDOSCOPE_PANELS='kaleidoscope.panels.timer.TimerPanel')
def test_panels_load_refuses_a_setting_that_is_not_a_list() -> None:
    with pytest.raises(ImproperlyConfigured, match='must be a list or tuple, not str'):
        panels_load()


@override_settings(KALEIDOSCOPE_PANELS=['kaleidoscope.registry.panels_load'])
def test_panels_load_refuses_an_entry_that_is_not_a_class() -> None:
    with pytest.raises(ImproperlyConfigured, match='is not a class'):
        panels_load()


@override_settings(KALEIDOSCOPE_PANELS=['kaleidoscope.registry.PanelRegistry'])
def test_panels_load_refuses_a_class_that_is_not_a_panel() -> None:
    with pytest.raises(ImproperlyConfigured, match='is not a subclass of Panel'):
        panels_load()


def test_enabling_an_isolated_panel_disables_the_other_isolated_panels() -> None:
    recorder = _Recorder()
    normal = _PanelSync('normal', recorder)
    first = _PanelSync('first', recorder, isolate=True)
    second = _PanelSync('second', recorder, isolate=True)
    first.enabled = False
    second.enabled = False
    panel_registry = PanelRegistry([normal, first, second])

    panel_registry.enabled_set(first, enabled=True)

    assert panel_registry.active() == [first]

    panel_registry.enabled_set(second, enabled=True)

    assert first.enabled is False
    assert normal.enabled is True
    assert panel_registry.active() == [second]

    panel_registry.enabled_set(second, enabled=False)

    assert panel_registry.active() == [normal]


def test_registry_keeps_only_the_first_isolated_panel_enabled_at_startup() -> None:
    recorder = _Recorder()
    first = _PanelSync('first', recorder, isolate=True)
    second = _PanelSync('second', recorder, isolate=True)
    panel_registry = PanelRegistry([first, second])

    assert first.enabled is True
    assert second.enabled is False
    assert panel_registry.active() == [first]


def test_two_isolated_panels_enabled_behind_the_registry_fail_loudly() -> None:
    recorder = _Recorder()
    first = _PanelSync('first', recorder, isolate=True)
    second = _PanelSync('second', recorder, isolate=True)
    panel_registry = PanelRegistry([first, second])
    second.enabled = True
    pattern = "only one isolated panel may be enabled at a time: \\['first', 'second'\\]"

    with pytest.raises(RuntimeError, match=pattern):
        panel_registry.active()


def test_isolation_uninstalls_the_suspended_panels_and_restores_them_after() -> None:
    recorder = _Recorder()
    installable = _PanelInstallable('installable', recorder)
    isolated = _PanelSync('isolated', recorder, isolate=True)
    isolated.enabled = False
    panel_registry = PanelRegistry([installable, isolated])

    panel_registry.enabled_set(isolated, enabled=True)
    panel_registry.enabled_set(isolated, enabled=False)

    assert recorder.events == [
        'installable:install',
        'installable:uninstall',
        'installable:install',
    ]


def test_enabled_set_refuses_a_value_that_is_not_a_bool() -> None:
    panel = _PanelSync('panel', _Recorder())
    panel_registry = PanelRegistry([panel])

    with pytest.raises(TypeError, match='enabled must be a bool'):
        panel_registry.enabled_set(panel, enabled=1)  # ty:ignore[invalid-argument-type]


def test_enabled_set_refuses_a_panel_from_another_registry() -> None:
    recorder = _Recorder()
    panel_registry = PanelRegistry([_PanelSync('panel', recorder)])

    with pytest.raises(ValueError, match="'panel' is not registered"):
        panel_registry.enabled_set(_PanelSync('panel', recorder), enabled=False)


def test_hooks_refuse_a_panel_list_from_another_registry(request_factory: RequestFactory) -> None:
    recorder = _Recorder()
    panel_registry = PanelRegistry([_PanelSync('panel', recorder)])
    stranger = [_PanelSync('stranger', recorder)]
    context = KaleidoscopeContext(panels=stranger)
    request = request_factory.get('/')

    with pytest.raises(ValueError, match="'stranger' is not registered"):
        panel_registry.process_request(request, context, stranger)

    with pytest.raises(ValueError, match="'stranger' is not registered"):
        panel_registry.process_response(request, HttpResponse(), context, stranger)

    assert recorder.events == []


def test_get_refuses_an_identifier_that_is_not_text() -> None:
    panel_registry = PanelRegistry([_PanelSync('panel', _Recorder())])

    with pytest.raises(TypeError, match='panel_id must be text'):
        panel_registry.get(7)  # ty:ignore[invalid-argument-type]


def test_get_fails_loudly_for_a_panel_renamed_after_registration() -> None:
    panel = _PanelSync('panel', _Recorder())
    panel_registry = PanelRegistry([panel])
    panel.panel_id = 'renamed'

    with pytest.raises(RuntimeError, match="now reports 'renamed'"):
        panel_registry.get('panel')


def test_hooks_refuse_arguments_of_the_wrong_kind(request_factory: RequestFactory) -> None:
    recorder = _Recorder()
    panel = _PanelSync('panel', recorder)
    panel_registry = PanelRegistry([panel])
    panels = [panel]
    context = KaleidoscopeContext(panels=panels)
    request = request_factory.get('/')

    with pytest.raises(TypeError, match='request must be an HttpRequest: dict'):
        panel_registry.process_request({}, context, panels)  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='context must be a KaleidoscopeContext: dict'):
        panel_registry.process_request(request, {}, panels)  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='response must be an HttpResponseBase: str'):
        panel_registry.process_response(
            request,
            'done',  # ty:ignore[invalid-argument-type]
            context,
            panels,
        )

    assert recorder.events == []
