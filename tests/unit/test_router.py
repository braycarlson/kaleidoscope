from __future__ import annotations

import pytest

from types import SimpleNamespace
from typing import TYPE_CHECKING

from django.http import HttpResponse

from kaleidoscope import router
from kaleidoscope.panels.timer import TimerPanel
from kaleidoscope.registry import PanelRegistry
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX, Router

from tests.toolbar import (
    PANEL_IDS_DEFAULT,
    PANEL_IDS_ISOLATED,
    json_read,
    panel_action,
    panel_data,
    panel_toggle,
    panels_listed,
)

if TYPE_CHECKING:
    from pathlib import Path

    from django.test import Client, RequestFactory


class _StaticPathFailing:
    def resolve(self) -> Path:
        message = 'the filesystem refused to resolve the path'
        raise OSError(message)


class _StaticDirectoryFailing:
    def __truediv__(self, name: str) -> _StaticPathFailing:
        _ = name

        return _StaticPathFailing()


def test_panel_list_names_every_default_panel_in_order(toolbar_client: Client) -> None:
    panels = panels_listed(toolbar_client)

    assert tuple(panel['id'] for panel in panels) == PANEL_IDS_DEFAULT

    for panel in panels:
        assert set(panel) == {'enabled', 'id', 'isolate', 'summary', 'title'}
        assert panel['isolate'] is (panel['id'] in PANEL_IDS_ISOLATED)
        assert panel['enabled'] is (panel['id'] not in PANEL_IDS_ISOLATED)
        assert isinstance(panel['summary'], str)


@pytest.mark.django_db
@pytest.mark.parametrize('panel_id', PANEL_IDS_DEFAULT)
def test_every_panel_answers_its_data_as_json(toolbar_client: Client, panel_id: str) -> None:
    toolbar_client.get('/work/?queries=2&templates=1&cache=set:alpha')

    assert isinstance(panel_data(toolbar_client, panel_id), dict)


@pytest.mark.parametrize('site', ['cross-site', 'same-site'])
def test_a_foreign_site_cannot_drive_the_toolbar(toolbar_client: Client, site: str) -> None:
    url = f'{KALEIDOSCOPE_URL_PREFIX}panels/profiling/enable/'
    response = toolbar_client.get(url, headers={'Sec-Fetch-Site': site})

    assert response.status_code == 403

    enabled = {panel['id']: panel['enabled'] for panel in panels_listed(toolbar_client)}

    assert enabled['profiling'] is False


@pytest.mark.parametrize('site', ['none', 'same-origin'])
def test_the_page_and_the_address_bar_drive_the_toolbar(toolbar_client: Client, site: str) -> None:
    url = f'{KALEIDOSCOPE_URL_PREFIX}panels/cache/disable/'
    response = toolbar_client.get(url, headers={'Sec-Fetch-Site': site})

    assert json_read(response) == {'enabled': False}


def test_disabling_and_enabling_a_panel_is_reflected_in_the_list(toolbar_client: Client) -> None:
    response = panel_toggle(toolbar_client, 'cache', enabled=False)

    assert json_read(response) == {'enabled': False}

    enabled = {panel['id']: panel['enabled'] for panel in panels_listed(toolbar_client)}

    assert enabled['cache'] is False

    response = panel_toggle(toolbar_client, 'cache', enabled=True)

    assert json_read(response) == {'enabled': True}

    enabled = {panel['id']: panel['enabled'] for panel in panels_listed(toolbar_client)}

    assert enabled['cache'] is True


def test_enabling_an_isolated_panel_disables_the_other_isolated_panels(
    toolbar_client: Client,
) -> None:
    panel_toggle(toolbar_client, 'memory', enabled=True)
    panel_toggle(toolbar_client, 'profiling', enabled=True)

    enabled = {panel['id']: panel['enabled'] for panel in panels_listed(toolbar_client)}

    assert enabled['memory'] is False
    assert enabled['profiling'] is True
    assert enabled['line_profiling'] is False
    assert enabled['queries'] is True


@pytest.mark.parametrize(
    'path',
    [
        'panels/missing/data/',
        'panels/queries/',
        'panels/queries/unknown/',
        'panels/queries/action/unknown/',
        'panels/queries/data/extra/',
        'panels',
        'elsewhere/',
        '',
        'static/missing.js',
        'static/../router.py',
        'static/..%2Frouter.py',
        'static/%2e%2e/router.py',
        'static/%00.js',
        'static/',
    ],
)
def test_unknown_toolbar_paths_answer_not_found(toolbar_client: Client, path: str) -> None:
    response = toolbar_client.get(f'{KALEIDOSCOPE_URL_PREFIX}{path}')

    assert response.status_code == 404


@pytest.mark.parametrize(
    ('filename', 'content_type'),
    [('kaleidoscope.js', 'application/javascript'), ('kaleidoscope.css', 'text/css')],
)
def test_static_assets_are_served_with_their_content_type(
    toolbar_client: Client,
    filename: str,
    content_type: str,
) -> None:
    response = toolbar_client.get(f'{KALEIDOSCOPE_URL_PREFIX}static/{filename}')

    assert response.status_code == 200
    assert response['Content-Type'] == content_type
    assert len(response.content) > 1000


def test_static_assets_are_revalidated_instead_of_downloaded_again(toolbar_client: Client) -> None:
    path = f'{KALEIDOSCOPE_URL_PREFIX}static/kaleidoscope.js'
    response = toolbar_client.get(path)

    assert response['Cache-Control'] == 'no-cache'
    assert response['ETag'].startswith('"')
    assert response['Last-Modified'].endswith('GMT')

    revalidated = toolbar_client.get(path, headers={'If-None-Match': response['ETag']})

    assert revalidated.status_code == 304
    assert revalidated.content == b''
    assert revalidated['ETag'] == response['ETag']

    unchanged = toolbar_client.get(path, headers={'If-Modified-Since': response['Last-Modified']})

    assert unchanged.status_code == 304

    stale = toolbar_client.get(path, headers={'If-None-Match': '"stale"'})

    assert stale.status_code == 200
    assert stale.content == response.content


@pytest.mark.django_db
def test_a_panel_whose_data_raises_answers_a_json_error(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(self: TimerPanel) -> dict:
        _ = self
        message = 'data is broken'

        raise RuntimeError(message)

    monkeypatch.setattr(TimerPanel, 'get_data', broken)

    response = toolbar_client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/timer/data/')

    assert response.status_code == 500
    assert json_read(response) == {'error': 'The timer panel failed to build its data.'}
    assert 'data is broken' in caplog.text


def test_a_panel_whose_summary_raises_still_appears_in_the_list(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
) -> None:
    def broken(self: TimerPanel) -> str:
        _ = self
        message = 'summary is broken'

        raise RuntimeError(message)

    monkeypatch.setattr(TimerPanel, 'get_summary', broken)

    panels = {panel['id']: panel for panel in panels_listed(toolbar_client)}

    assert panels['timer']['summary'] == ''
    assert panels['timer']['title'] == 'Timer'
    assert len(panels) == len(PANEL_IDS_DEFAULT)


def test_a_panel_whose_action_raises_answers_a_json_error(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
) -> None:
    def broken(self: TimerPanel, action: str, request: object) -> None:
        _ = self
        _ = request
        message = f'{action} is broken'

        raise RuntimeError(message)

    monkeypatch.setattr(TimerPanel, 'handle_action', broken)

    response = panel_action(toolbar_client, 'timer', 'anything')

    assert response.status_code == 500
    assert 'timer' in json_read(response)['error']


@pytest.mark.django_db
def test_queries_actions_clear_and_toggle_tracking(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?queries=1')

    assert json_read(panel_action(toolbar_client, 'queries', 'clear')) == {'success': True}
    assert panel_data(toolbar_client, 'queries')['requests'] == []

    assert json_read(panel_action(toolbar_client, 'queries', 'track-page-off')) == {
        'track_page': False,
    }

    toolbar_client.get('/work/?queries=1')

    assert panel_data(toolbar_client, 'queries')['requests'] == []
    assert panel_data(toolbar_client, 'queries')['track_page'] is False

    panel_action(toolbar_client, 'queries', 'track-page-on')
    panel_action(toolbar_client, 'queries', 'track-ajax-off')

    toolbar_client.get('/work/?queries=1')
    toolbar_client.get('/work/?queries=1', headers={'X-Requested-With': 'XMLHttpRequest'})

    requests = panel_data(toolbar_client, 'queries')['requests']

    assert [request['is_ajax'] for request in requests] == [False]

    panel_action(toolbar_client, 'queries', 'track-ajax-on')
    toolbar_client.get('/work/?queries=1', headers={'X-Requested-With': 'XMLHttpRequest'})

    requests = panel_data(toolbar_client, 'queries')['requests']

    assert [request['is_ajax'] for request in requests] == [False, True]


@pytest.mark.parametrize('summary', [None, 7, b'bytes', ['text'], object()])
def test_a_panel_whose_summary_is_not_text_lists_an_empty_summary(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
    summary: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def malformed(self: TimerPanel) -> object:
        _ = self

        return summary

    monkeypatch.setattr(TimerPanel, 'get_summary', malformed)

    panels = {panel['id']: panel for panel in panels_listed(toolbar_client)}

    assert panels['timer']['summary'] == ''
    assert len(panels) == len(PANEL_IDS_DEFAULT)
    assert 'timer' in caplog.text


@pytest.mark.parametrize('answer', [{'ok': True}, 'text', 0, object()])
def test_a_panel_whose_action_answers_no_response_answers_a_json_error(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
    answer: object,
) -> None:
    def malformed(self: TimerPanel, action: str, request: object) -> object:
        _ = self
        _ = action
        _ = request

        return answer

    monkeypatch.setattr(TimerPanel, 'handle_action', malformed)

    response = panel_action(toolbar_client, 'timer', 'anything')

    assert response.status_code == 500
    assert 'timer' in json_read(response)['error']


def test_a_panel_whose_action_answers_a_response_passes_it_through(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
) -> None:
    def answered(self: TimerPanel, action: str, request: object) -> HttpResponse:
        _ = self
        _ = request

        return HttpResponse(f'answered {action}', content_type='text/plain')

    monkeypatch.setattr(TimerPanel, 'handle_action', answered)

    response = panel_action(toolbar_client, 'timer', 'anything')

    assert response.status_code == 200
    assert response.content == b'answered anything'


def test_a_panel_without_actions_answers_not_found(toolbar_client: Client) -> None:
    assert panel_action(toolbar_client, 'timer', 'anything').status_code == 404


def test_a_static_name_too_long_for_the_filesystem_answers_not_found(
    toolbar_client: Client,
) -> None:
    name = 'a' * 5_000
    response = toolbar_client.get(f'{KALEIDOSCOPE_URL_PREFIX}static/{name}.js')

    assert response.status_code == 404


def test_a_toolbar_request_never_saves_the_session(request_factory: RequestFactory) -> None:
    request = request_factory.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/')
    request.session = SimpleNamespace(modified=True)
    registry = PanelRegistry([TimerPanel()])
    response = Router(registry).dispatch(request, is_shown=True)

    assert response.status_code == 200
    assert request.session.modified is False


def test_a_static_link_that_leaves_the_static_directory_answers_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    toolbar_client: Client,
) -> None:
    directory = tmp_path / 'static'
    link = directory / 'link.js'
    outside = tmp_path / 'outside.js'

    directory.mkdir()
    outside.write_text('secret', encoding='utf-8')
    link.symlink_to(outside)
    monkeypatch.setattr(router, 'STATIC_DIR', directory)
    monkeypatch.setattr(router, '_STATIC_DIR_RESOLVED', directory.resolve())

    response = toolbar_client.get(f'{KALEIDOSCOPE_URL_PREFIX}static/link.js')

    assert response.status_code == 404


def test_a_static_link_that_loops_answers_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    toolbar_client: Client,
) -> None:
    directory = tmp_path / 'static'
    link = directory / 'loop.js'

    directory.mkdir()
    link.symlink_to(link)
    monkeypatch.setattr(router, 'STATIC_DIR', directory)
    monkeypatch.setattr(router, '_STATIC_DIR_RESOLVED', directory.resolve())

    response = toolbar_client.get(f'{KALEIDOSCOPE_URL_PREFIX}static/loop.js')

    assert response.status_code == 404


def test_a_static_path_the_filesystem_cannot_resolve_answers_not_found(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
) -> None:
    directory = _StaticDirectoryFailing()

    monkeypatch.setattr(router, 'STATIC_DIR', directory)

    response = toolbar_client.get(f'{KALEIDOSCOPE_URL_PREFIX}static/kaleidoscope.js')

    assert response.status_code == 404


def test_a_router_refuses_something_that_is_not_a_registry() -> None:
    with pytest.raises(TypeError, match='registry must be a PanelRegistry: dict'):
        Router({})  # ty:ignore[invalid-argument-type]


def test_dispatch_refuses_arguments_of_the_wrong_kind(request_factory: RequestFactory) -> None:
    router_instance = Router(PanelRegistry([TimerPanel()]))
    request = request_factory.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/')

    with pytest.raises(TypeError, match='request must be an HttpRequest: dict'):
        router_instance.dispatch({}, is_shown=True)  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match="is_shown must be a bool: 'yes'"):
        router_instance.dispatch(request, is_shown='yes')  # ty:ignore[invalid-argument-type]


def test_dispatch_refuses_a_path_outside_the_toolbar(request_factory: RequestFactory) -> None:
    router_instance = Router(PanelRegistry([TimerPanel()]))
    request = request_factory.get('/elsewhere/')

    with pytest.raises(ValueError, match="only serves /__kaleidoscope__/, not '/elsewhere/'"):
        router_instance.dispatch(request, is_shown=True)
