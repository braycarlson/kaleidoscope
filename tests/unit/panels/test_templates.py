from __future__ import annotations

import json

import pytest

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.http import HttpResponse
from django.template import Context, Engine, Template
from django.test.signals import template_rendered
from django.test.utils import instrumented_test_render

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panels import templates as templates_panel
from kaleidoscope.panels.templates import (
    TEMPLATE_VALUE_PATH_LENGTH_MAX,
    TEMPLATE_VALUE_STEPS_MAX,
    TemplateRender,
    TemplatesPanel,
    _context_items,
    _render_wrapper_build,
)
from kaleidoscope.patch import is_patched
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX

from tests.testapp.work import spin_for_profile
from tests.toolbar import (
    HEADERS_AJAX,
    HEADERS_HIDDEN,
    json_read,
    panel_data,
    panel_toggle,
    panels_listed,
)

if TYPE_CHECKING:
    from django.test import Client, RequestFactory

    from tests.testapp.models import Author


class _Slow:
    def __str__(self) -> str:
        spin_for_profile(1)

        return 'slow'


class _Unrenderable:
    def __str__(self) -> str:
        message = 'the value cannot be rendered'
        raise RuntimeError(message)


def _layout_engine() -> Engine:
    templates = {
        'base.html': '<main>{% block content %}{% endblock %}</main>{% include "footer.html" %}',
        'footer.html': '<footer>{{ value }}</footer>',
        'page.html': (
            '{% extends "base.html" %}'
            '{% block content %}{% include "row.html" %}{% endblock %}'
        ),
        'row.html': '<p>{{ value }}</p>',
    }

    loader = ('django.template.loaders.locmem.Loader', templates)
    loaders = [loader]

    return Engine(loaders=loaders)


def _value_get(client: Client, *, path: str, template: str = '0') -> HttpResponse:
    query = urlencode({'path': path, 'template': template})

    return client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/templates/action/value/?{query}')


@pytest.mark.django_db
def test_templates_panel_lists_each_render_of_the_last_page(
    toolbar_client: Client,
    library: list[Author],
) -> None:
    _ = library

    toolbar_client.get('/page/')

    data = panel_data(toolbar_client, 'templates')
    names = [template['name'] for template in data['templates']]

    assert names == ['testapp/page.html', 'testapp/fragment.html']
    assert data['count'] == 2
    assert data['total_time'] >= 0.0
    assert 'authors' in data['templates'][0]['context_keys']
    assert 'title' in data['templates'][0]['context_keys']


@pytest.mark.django_db
def test_templates_panel_hides_private_and_builtin_context_keys(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?templates=1')

    keys = panel_data(toolbar_client, 'templates')['templates'][0]['context_keys']

    assert keys == ['index', 'token']


@pytest.mark.django_db
def test_templates_panel_ignores_ajax_requests(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?templates=2')
    toolbar_client.get('/work/?templates=4', headers=HEADERS_AJAX)

    assert panel_data(toolbar_client, 'templates')['count'] == 2


@pytest.mark.django_db
def test_templates_panel_names_inline_templates(toolbar_client: Client) -> None:
    toolbar_client.get('/plain/')

    context = Context({'value': 1})
    template = Template('{{ value }}')

    templates_panel._collecting.set([])
    template.render(context)
    collected = templates_panel._collecting.get()

    templates_panel._collecting.set(None)

    assert [render.name for render in collected] == ['<inline>']


@pytest.mark.django_db
def test_templates_panel_stops_recording_at_the_per_request_maximum(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
) -> None:
    monkeypatch.setattr(templates_panel, 'TEMPLATES_PER_REQUEST_MAX', 2)

    toolbar_client.get('/work/?templates=5')

    assert panel_data(toolbar_client, 'templates')['count'] == 2


@pytest.mark.django_db
def test_templates_summary_counts_templates_and_time(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?templates=3')

    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}

    assert summaries['templates'].startswith('3 templates, ')
    assert summaries['templates'].endswith(' ms')


@pytest.mark.django_db
def test_value_action_reads_a_context_variable(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?templates=1&token=valued')

    path = json.dumps([{'kind': 'key', 'name': 'token'}])
    response = _value_get(toolbar_client, path=path)

    assert response.status_code == 200
    assert json_read(response) == {'value': {'type': 'string', 'truncated': 0, 'value': 'valued'}}


@pytest.mark.django_db
def test_value_action_walks_into_a_queryset(toolbar_client: Client, library: list[Author]) -> None:
    toolbar_client.get('/page/')

    path = json.dumps([
        {'kind': 'key', 'name': 'authors'},
        {'kind': 'item', 'index': 0},
        {'kind': 'attr', 'name': 'name'},
    ])

    response = _value_get(toolbar_client, path=path)

    assert response.status_code == 200
    assert json_read(response)['value']['value'] == library[0].name


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('path', 'template', 'status'),
    [
        ('[]', '7', 404),
        ('[]', '-1', 404),
        ('[]', 'x', 400),
        ('{"kind": "key"}', '0', 400),
        ('not json', '0', 400),
        ('[{"kind": "key", "name": "missing"}]', '0', 400),
        ('[{"kind": "key", "name": "token"}, {"kind": "attr", "name": "__class__"}]', '0', 400),
        ('[' * 5000 + ']' * 5000, '0', 400),
        ('[' * 2000 + ']' * 2000, '0', 400),
        ('[{"kind": "key", "name": "token"}]' + ' ' * TEMPLATE_VALUE_PATH_LENGTH_MAX, '0', 400),
    ],
)
def test_value_action_refuses_a_bad_request_without_failing(
    toolbar_client: Client,
    path: str,
    template: str,
    status: int,
) -> None:
    toolbar_client.get('/work/?templates=1')

    response = _value_get(toolbar_client, path=path, template=template)

    assert response.status_code == status
    assert 'error' in json_read(response)


@pytest.mark.django_db
def test_value_action_refuses_a_path_deeper_than_the_maximum(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?templates=1')

    steps = [{'kind': 'item', 'index': 0}] * (TEMPLATE_VALUE_STEPS_MAX + 1)
    response = _value_get(toolbar_client, path=json.dumps(steps))

    assert response.status_code == 400
    assert json_read(response) == {'error': 'path too deep'}


def test_install_wraps_render_once_and_uninstall_restores_it() -> None:
    original = Template._render
    first = TemplatesPanel()
    second = TemplatesPanel()

    first.install()
    second.install()

    assert is_patched(Template._render)
    assert Template._render.__wrapped__ is original

    second.uninstall()

    assert Template._render is original


def test_unknown_actions_are_not_handled() -> None:
    panel = TemplatesPanel()

    assert panel.handle_action('missing', None) is None  # ty:ignore[invalid-argument-type]


def test_context_items_read_a_plain_dictionary_and_keep_only_public_text_keys() -> None:
    context = {'shown': 1, '_private': 2, 'True': 3, 7: 'numbered'}

    assert _context_items(context) == {'shown': 1}


def test_context_items_read_nothing_from_a_value_that_is_no_context() -> None:
    assert _context_items(['not', 'a', 'context']) == {}


def test_context_items_skip_a_layer_that_is_no_dictionary() -> None:
    context = Context({'shown': 1})
    context.dicts.append(['not', 'a', 'dictionary'])

    assert _context_items(context) == {'shown': 1}


def test_context_items_stop_at_the_key_maximum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(templates_panel, 'CONTEXT_KEYS_MAX', 2)

    context = {'first': 1, 'second': 2, 'third': 3}

    assert _context_items(context) == {'first': 1, 'second': 2}


def test_a_render_whose_context_cannot_be_read_is_still_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def items_broken(context: object) -> dict:
        _ = context
        message = 'the context is unreadable'

        raise RuntimeError(message)

    monkeypatch.setattr(templates_panel, '_context_items', items_broken)

    renders: list = []
    template = Template('{{ shown }}', name='unreadable.html')
    context = Context({'shown': 'yes'})

    TemplatesPanel().install()
    templates_panel._collecting.set(renders)

    assert template.render(context) == 'yes'
    assert [(render.name, render.context) for render in renders] == [('unreadable.html', {})]


@pytest.mark.django_db
def test_isolation_restores_the_original_render_until_it_ends(toolbar_client: Client) -> None:
    original = Template._render

    toolbar_client.get('/plain/')

    assert Template._render.__wrapped__ is original

    panel_toggle(toolbar_client, 'profiling', enabled=True)

    assert Template._render is original

    panel_toggle(toolbar_client, 'profiling', enabled=False)

    assert Template._render.__wrapped__ is original


@pytest.mark.django_db
def test_a_render_outside_a_collecting_request_passes_straight_through(
    toolbar_client: Client,
    library: list[Author],
) -> None:
    _ = library

    toolbar_client.get('/page/')
    response = toolbar_client.get('/page/', headers=HEADERS_HIDDEN)

    assert is_patched(Template._render)
    assert 'author-0' in response.content.decode()
    assert panel_data(toolbar_client, 'templates')['count'] == 2


def test_value_action_refuses_something_that_is_not_a_request() -> None:
    panel = TemplatesPanel()

    with pytest.raises(TypeError, match='needs an HttpRequest, not NoneType'):
        panel.handle_action('value', None)  # ty:ignore[invalid-argument-type]


def test_templates_panel_refuses_more_renders_than_it_holds(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    monkeypatch.setattr(templates_panel, 'TEMPLATES_PER_REQUEST_MAX', 1)

    panel = TemplatesPanel()
    request = request_factory.get('/')
    response = HttpResponse()
    context = KaleidoscopeContext()
    first = TemplateRender(context={}, depth=0, duration_ms=0.0, name='first.html')
    second = TemplateRender(context={}, depth=0, duration_ms=0.0, name='second.html')
    renders = [first, second]

    templates_panel._collecting.set(renders)

    with pytest.raises(RuntimeError, match='holds 2 renders, over 1'):
        panel.process_response(request, response, context)

    assert templates_panel._collecting.get() is None
    assert panel.get_data() == {}


def test_templates_panel_lists_an_extended_parent_and_counts_nested_time_once(
    request_factory: RequestFactory,
) -> None:
    panel = TemplatesPanel()
    context = KaleidoscopeContext()
    request = request_factory.get('/')
    template = _layout_engine().get_template('page.html')

    panel.install()
    panel.process_request(request, context)
    template.render(Context({'value': _Slow()}))
    panel.process_response(request, HttpResponse(), context)

    data = panel.get_data()
    names = [render['name'] for render in data['templates']]

    assert names == ['page.html', 'base.html', 'row.html', 'footer.html']
    assert data['templates'][2]['duration_ms'] > 0.0
    assert data['total_time'] == data['templates'][0]['duration_ms']


def test_a_render_that_fails_still_restores_the_depth() -> None:
    expected = [('page.html', 0), ('base.html', 1), ('row.html', 2)]
    renders: list = []
    template = _layout_engine().get_template('page.html')

    TemplatesPanel().install()
    templates_panel._collecting.set(renders)

    with pytest.raises(RuntimeError, match='the value cannot be rendered'):
        template.render(Context({'value': _Unrenderable()}))

    assert [(render.name, render.depth) for render in renders] == expected
    assert templates_panel._depth.get() == 0


@pytest.mark.django_db
def test_the_page_template_sees_the_variables_of_the_context_processors(
    toolbar_client: Client,
    library: list[Author],
) -> None:
    _ = library

    toolbar_client.get('/page/')

    keys = panel_data(toolbar_client, 'templates')['templates'][0]['context_keys']

    assert 'authors' in keys
    assert 'csrf_token' in keys


def test_install_keeps_the_instrumentation_of_the_render_it_wraps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names: list[str] = []
    template = Template('{{ shown }}', name='instrumented.html')

    def rendered(sender: object, **kwargs: object) -> None:
        _ = sender

        names.append(kwargs['template'].name)

    monkeypatch.setattr(Template, '_render', instrumented_test_render)
    template_rendered.connect(rendered)

    try:
        TemplatesPanel().install()
        template.render(Context({'shown': 'yes'}))
    finally:
        template_rendered.disconnect(rendered)

    assert Template._render.__wrapped__ is instrumented_test_render
    assert names == ['instrumented.html']


def test_uninstall_leaves_a_render_it_does_not_own(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Template, '_render', instrumented_test_render)

    TemplatesPanel().uninstall()

    assert Template._render is instrumented_test_render


def test_wrapping_a_render_twice_is_refused() -> None:
    TemplatesPanel().install()

    with pytest.raises(RuntimeError, match='already wrapped by kaleidoscope'):
        _render_wrapper_build(Template._render)


def test_wrapping_something_that_cannot_render_is_refused() -> None:
    with pytest.raises(TypeError, match='original must be callable, not NoneType'):
        _render_wrapper_build(None)  # ty:ignore[invalid-argument-type]
