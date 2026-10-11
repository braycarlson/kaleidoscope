from __future__ import annotations

import asyncio
import contextlib

import pytest

from types import MappingProxyType
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync, sync_to_async
from django.core.cache import cache
from django.db import connection, connections
from django.http import HttpResponse
from django.test import AsyncClient, AsyncRequestFactory, Client, override_settings

from kaleidoscope import middleware as middleware_module
from kaleidoscope.injector import HEADER_REQUEST_ID, HEADER_SERVER_TIMING
from kaleidoscope.middleware import STATUS_CLIENT_CLOSED_REQUEST, KaleidoscopeMiddleware
from kaleidoscope.panels.cache import CachePanel
from kaleidoscope.panels.timer import TimerPanel
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX

from tests.testapp import panels as recording
from tests.testapp.models import Author
from tests.toolbar import (
    HEADERS_AJAX,
    HEADERS_HIDDEN,
    async_get,
    json_read,
    panel_data,
    panels_listed,
    shell_text,
)

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.test import RequestFactory

    from kaleidoscope.panel import Panel


HEADERS_PAGE = MappingProxyType({'Accept': 'text/html'})

PANELS_THREAD_RECORDING = (
    'tests.testapp.panels.ThreadRecordingPanel',
    'tests.testapp.panels.ThreadFollowingPanel',
)


class _HopRecorder:
    def __init__(self) -> None:
        self.functions: list[object] = []

    def sync_to_async(self, function: object, **keywords: object) -> object:
        self.functions.append(function)

        return sync_to_async(function, **keywords)  # ty:ignore[invalid-argument-type]


def _panels_on_loop_stranger(request: HttpRequest, panels: list[Panel]) -> list[Panel]:
    _ = request
    _ = panels

    return [TimerPanel()]


def _show_callback_broken(request: HttpRequest) -> bool:
    _ = request
    message = 'the show callback is broken'

    raise RuntimeError(message)


def _view_plain(request: HttpRequest) -> HttpResponse:
    _ = request

    return HttpResponse('<html><body>done</body></html>')


async def _view_plain_async(request: HttpRequest) -> HttpResponse:
    _ = request

    return HttpResponse('<html><body>done</body></html>')


@pytest.mark.django_db
def test_page_request_carries_the_shell_and_a_request_id(toolbar_client: Client) -> None:
    response = toolbar_client.get('/plain/')
    content = response.content.decode()

    assert response.status_code == 200
    assert content.count(shell_text()) == 1
    assert content.index(shell_text()) < content.index('</body>')
    assert len(response[HEADER_REQUEST_ID]) == 32
    assert int(response['Content-Length']) == len(response.content)


@pytest.mark.django_db
def test_ajax_request_carries_a_request_id_but_no_shell(toolbar_client: Client) -> None:
    response = toolbar_client.get('/plain/', headers=HEADERS_AJAX)

    assert shell_text() not in response.content.decode()
    assert len(response[HEADER_REQUEST_ID]) == 32


@pytest.mark.django_db
def test_ignored_path_is_left_untouched(toolbar_client: Client) -> None:
    response = toolbar_client.get('/ignored/')

    assert shell_text() not in response.content.decode()
    assert HEADER_REQUEST_ID not in response
    assert HEADER_SERVER_TIMING not in response
    assert panel_data(toolbar_client, 'queries')['requests'] == []


@pytest.mark.django_db
def test_hidden_request_is_left_untouched(toolbar_client: Client) -> None:
    response = toolbar_client.get('/plain/', headers=HEADERS_HIDDEN)

    assert shell_text() not in response.content.decode()
    assert HEADER_REQUEST_ID not in response
    assert panel_data(toolbar_client, 'queries')['requests'] == []


def test_hidden_request_finds_no_toolbar_endpoint(toolbar_client: Client) -> None:
    paths = (
        f'{KALEIDOSCOPE_URL_PREFIX}panels/',
        f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/data/',
        f'{KALEIDOSCOPE_URL_PREFIX}static/kaleidoscope.js',
    )

    for path in paths:
        response = toolbar_client.get(path, headers=HEADERS_HIDDEN)

        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('headers', 'is_ajax'),
    [
        ({}, False),
        ({'X-Requested-With': 'XMLHttpRequest'}, True),
        ({'Sec-Fetch-Dest': 'document'}, False),
        ({'Sec-Fetch-Dest': 'empty'}, True),
        ({'Sec-Fetch-Dest': 'document', 'X-Requested-With': 'XMLHttpRequest'}, True),
        ({'Accept': 'application/json'}, True),
        ({'Accept': '*/*'}, True),
        ({'Accept': 'text/html,application/xhtml+xml;q=0.9'}, False),
    ],
)
def test_request_kind_follows_the_browser_headers(
    toolbar_client: Client,
    headers: dict[str, str],
    is_ajax: bool,
) -> None:
    toolbar_client.get('/work/?queries=1', headers=headers)

    requests = panel_data(toolbar_client, 'queries')['requests']

    assert len(requests) == 1
    assert requests[0]['is_ajax'] is is_ajax


@pytest.mark.django_db
@override_settings(KALEIDOSCOPE_SHOW_CALLBACK='tests.unit.test_middleware._show_callback_broken')
def test_a_raising_show_callback_hides_the_toolbar_instead_of_failing_the_page(
    toolbar_client: Client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = toolbar_client.get('/plain/')

    assert response.status_code == 200
    assert shell_text() not in response.content.decode()
    assert 'show callback failed' in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    'method_name',
    ['process_request', 'process_response', 'get_server_timing'],
)
def test_a_panel_that_raises_never_changes_the_host_response(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
    method_name: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(*arguments: object) -> None:
        _ = arguments
        message = f'{method_name} is broken'

        raise RuntimeError(message)

    monkeypatch.setattr(CachePanel, method_name, broken)

    response = toolbar_client.get('/work/?queries=2&templates=1')
    content = response.content.decode()

    assert response.status_code == 200
    assert content.count(shell_text()) == 1
    assert 'cache' in caplog.text
    assert panel_data(toolbar_client, 'queries')['requests'][0]['query_count'] == 2


@pytest.mark.django_db
def test_disabling_the_queries_panel_mid_request_leaks_no_execute_wrapper(
    request_factory: RequestFactory,
) -> None:
    middleware: KaleidoscopeMiddleware

    def get_response(request: HttpRequest) -> HttpResponse:
        _ = request
        panel_registry = middleware._registry

        panel_registry.enabled_set(panel_registry.panels['queries'], enabled=False)
        Author.objects.count()

        return HttpResponse('<html><body>done</body></html>')

    middleware = KaleidoscopeMiddleware(get_response)
    request = request_factory.get('/plain/')
    response = middleware(request)

    assert response.status_code == 200
    assert connection.execute_wrappers == []
    assert middleware._registry.panels['queries'].store.summary['total_queries'] == 1


@pytest.mark.django_db
def test_enabling_an_isolated_panel_mid_request_still_finishes_the_others(
    request_factory: RequestFactory,
) -> None:
    middleware: KaleidoscopeMiddleware

    def get_response(request: HttpRequest) -> HttpResponse:
        _ = request
        panel_registry = middleware._registry

        panel_registry.enabled_set(panel_registry.panels['profiling'], enabled=True)
        Author.objects.count()

        return HttpResponse('<html><body>done</body></html>')

    middleware = KaleidoscopeMiddleware(get_response)
    request = request_factory.get('/plain/')

    middleware(request)

    assert connection.execute_wrappers == []
    assert middleware._registry.panels['queries'].store.summary['total_queries'] == 1


@pytest.mark.django_db
@override_settings(DEBUG_PROPAGATE_EXCEPTIONS=True)
def test_a_propagated_view_exception_still_runs_every_response_hook(library: list[Author]) -> None:
    _ = library
    client = Client(raise_request_exception=True)

    with pytest.raises(Exception, match='failed on purpose'):
        client.get('/work/?queries=3&fail=1')

    for alias in connections:
        assert connections[alias].execute_wrappers == []

    client.exc_info = None
    client.raise_request_exception = False
    requests = panel_data(client, 'queries')['requests']

    assert requests[0]['query_count'] == 3
    assert requests[0]['status_code'] == 500


async def _propagated_failure_records() -> list[dict]:
    async def view(request: HttpRequest) -> HttpResponse:
        _ = request

        await sync_to_async(_statement_run)()

        message = 'the async view failed on purpose'
        raise RuntimeError(message)

    middleware = KaleidoscopeMiddleware(view)
    factory = AsyncRequestFactory()

    with contextlib.suppress(RuntimeError):
        await middleware(factory.get('/plain/', headers={'Accept': 'text/html'}))

    response = await middleware(factory.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/data/'))

    return json_read(response)['requests']


@pytest.mark.django_db
def test_an_async_view_exception_still_runs_every_response_hook() -> None:
    records = async_to_sync(_propagated_failure_records)()

    assert [(record['status_code'], record['query_count']) for record in records] == [(500, 1)]
    assert not any(connections[alias].execute_wrappers for alias in connections)


@pytest.mark.django_db
def test_server_timing_reports_this_request_and_not_the_whole_store(
    toolbar_client: Client,
    library: list[Author],
) -> None:
    _ = library
    page = toolbar_client.get('/work/?queries=5&distinct=3')
    ajax = toolbar_client.get('/work/?queries=1', headers=HEADERS_AJAX)

    assert 'desc="SQL 5 queries"' in page[HEADER_SERVER_TIMING]
    assert 'desc="SQL 1 queries"' in ajax[HEADER_SERVER_TIMING]
    assert panel_data(toolbar_client, 'queries')['summary']['total_queries'] == 6


@pytest.mark.django_db
def test_server_timing_keeps_the_header_the_view_set(toolbar_client: Client) -> None:
    response = toolbar_client.get('/work/?timing=1&queries=1')
    header = response[HEADER_SERVER_TIMING]

    assert header.startswith('app;dur=1.5;desc="app", ')
    assert 'timer_total;dur=' in header


@pytest.mark.django_db
def test_async_page_request_carries_the_shell(toolbar_client_async: AsyncClient) -> None:
    response = async_get(toolbar_client_async, '/plain/')
    content = response.content.decode()

    assert content.count(shell_text()) == 1
    assert len(response[HEADER_REQUEST_ID]) == 32


@pytest.mark.django_db
def test_async_server_captures_the_queries_of_a_sync_view(
    toolbar_client_async: AsyncClient,
    library: list[Author],
) -> None:
    _ = library

    async_get(toolbar_client_async, '/work/?queries=4&distinct=2')

    response = async_get(toolbar_client_async, f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/data/')
    requests = json_read(response)['requests']

    assert requests[0]['query_count'] == 4
    assert connection.execute_wrappers == []


@pytest.mark.django_db
def test_async_server_captures_the_queries_of_an_async_view(
    toolbar_client_async: AsyncClient,
    library: list[Author],
) -> None:
    _ = library
    page = async_get(toolbar_client_async, '/async/')
    response = async_get(toolbar_client_async, f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/data/')
    requests = json_read(response)['requests']

    assert 'authors 3' in page.content.decode()
    assert requests[0]['query_count'] == 1


def _statement_run() -> None:
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')


async def _cancelled_request_records() -> list[dict]:
    entered = asyncio.Event()
    released = asyncio.Event()

    async def view(request: HttpRequest) -> HttpResponse:
        _ = request

        await sync_to_async(_statement_run)()
        entered.set()
        await released.wait()

        return HttpResponse('never sent')

    middleware = KaleidoscopeMiddleware(view)
    factory = AsyncRequestFactory()
    request = factory.get('/plain/', headers={'Accept': 'text/html'})
    coroutine = middleware(request)
    task = asyncio.ensure_future(coroutine)

    await entered.wait()
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task

    response = await middleware(factory.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/data/'))

    return json_read(response)['requests']


@pytest.mark.django_db
def test_a_cancelled_async_request_releases_its_capture_and_is_recorded() -> None:
    records = async_to_sync(_cancelled_request_records)()

    assert [(record['status_code'], record['query_count']) for record in records] == [
        (STATUS_CLIENT_CLOSED_REQUEST, 1),
    ]

    assert not any(connections[alias].execute_wrappers for alias in connections)


async def _lingering_query_records() -> list[dict]:
    released = asyncio.Event()
    second_entered = asyncio.Event()
    second_released = asyncio.Event()
    lingering: list[asyncio.Future] = []

    async def statement_late() -> None:
        await released.wait()
        await sync_to_async(_statement_run)()

    async def view(request: HttpRequest) -> HttpResponse:
        if request.path == '/second/':
            second_entered.set()
            await second_released.wait()

            return HttpResponse('{}', content_type='application/json')

        await sync_to_async(_statement_run)()

        task = asyncio.ensure_future(statement_late())

        lingering.append(task)

        return HttpResponse('{}', content_type='application/json')

    middleware = KaleidoscopeMiddleware(view)
    factory = AsyncRequestFactory()

    await middleware(factory.get('/first/', headers=dict(HEADERS_AJAX)))

    second = asyncio.ensure_future(middleware(factory.get('/second/', headers=dict(HEADERS_AJAX))))

    await second_entered.wait()
    released.set()
    await lingering[0]
    second_released.set()
    await second

    response = await middleware(factory.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/data/'))

    return json_read(response)['requests']


async def _lingering_cache_calls() -> tuple[list[dict], list[dict]]:
    released = asyncio.Event()
    lingering: list[asyncio.Future] = []

    async def cache_read_late() -> None:
        await released.wait()
        cache.get('late')

    async def view(request: HttpRequest) -> HttpResponse:
        _ = request

        cache.get('early')

        task = asyncio.ensure_future(cache_read_late())

        lingering.append(task)

        return HttpResponse('<html><body>page</body></html>')

    middleware = KaleidoscopeMiddleware(view)
    factory = AsyncRequestFactory()
    data_path = f'{KALEIDOSCOPE_URL_PREFIX}panels/cache/data/'

    await middleware(factory.get('/page/', headers={'Accept': 'text/html'}))

    before = json_read(await middleware(factory.get(data_path)))['calls']

    released.set()
    await lingering[0]

    after = json_read(await middleware(factory.get(data_path)))['calls']

    return before, after


@pytest.mark.django_db
def test_a_task_that_outlives_its_request_never_adds_to_the_stored_queries() -> None:
    records = async_to_sync(_lingering_query_records)()
    counts = [(record['path'], record['query_count'], len(record['queries'])) for record in records]

    assert counts == [('/first/', 1, 1), ('/second/', 0, 0)]
    assert not any(connections[alias].execute_wrappers for alias in connections)


@pytest.mark.django_db
def test_a_task_that_outlives_its_request_never_adds_to_the_cache_calls() -> None:
    before, after = async_to_sync(_lingering_cache_calls)()

    assert [call['args'] for call in before] == ["'early'"]
    assert after == before


@pytest.mark.django_db
def test_async_server_reports_its_timer_as_asgi(toolbar_client_async: AsyncClient) -> None:
    async_get(toolbar_client_async, '/plain/')

    response = async_get(toolbar_client_async, f'{KALEIDOSCOPE_URL_PREFIX}panels/timer/data/')

    assert json_read(response)['asgi'] is True


@pytest.mark.django_db
def test_async_server_collects_templates_and_cache_calls(
    toolbar_client_async: AsyncClient,
    library: list[Author],
) -> None:
    _ = library

    async_get(toolbar_client_async, '/work/?templates=2&cache=set:alpha,get:alpha')

    templates = async_get(toolbar_client_async, f'{KALEIDOSCOPE_URL_PREFIX}panels/templates/data/')
    cache = async_get(toolbar_client_async, f'{KALEIDOSCOPE_URL_PREFIX}panels/cache/data/')

    assert json_read(templates)['count'] == 2
    assert [call['method'] for call in json_read(cache)['calls']] == ['SET', 'GET']


@pytest.mark.django_db
def test_toolbar_requests_are_never_captured(toolbar_client: Client) -> None:
    toolbar_client.get('/plain/')
    panels_listed(toolbar_client)
    panel_data(toolbar_client, 'timer')

    requests = panel_data(toolbar_client, 'queries')['requests']

    assert [request['path'] for request in requests] == ['/plain/']


@pytest.mark.django_db
def test_async_hidden_and_ignored_requests_are_left_untouched(
    toolbar_client_async: AsyncClient,
) -> None:
    hidden = async_get(toolbar_client_async, '/plain/', headers=dict(HEADERS_HIDDEN))
    ignored = async_get(toolbar_client_async, '/ignored/')

    for response in (hidden, ignored):
        assert shell_text() not in response.content.decode()
        assert HEADER_REQUEST_ID not in response


@pytest.mark.django_db
@pytest.mark.parametrize('ignore_paths', [None, 7, '/plain/'])
def test_a_malformed_ignore_list_never_breaks_a_page(
    toolbar_client: Client,
    ignore_paths: object,
) -> None:
    with override_settings(KALEIDOSCOPE_IGNORE_PATHS=ignore_paths):
        response = toolbar_client.get('/plain/')

    assert response.status_code == 200
    assert response.content.decode().count(shell_text()) == 1


@pytest.mark.django_db
@override_settings(KALEIDOSCOPE_IGNORE_PATHS=[None, '/ignored/'])
def test_an_ignore_list_with_a_stray_entry_still_ignores_its_prefixes(
    toolbar_client: Client,
) -> None:
    response = toolbar_client.get('/ignored/')

    assert response.status_code == 200
    assert shell_text() not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('path', 'following_on_loop'),
    [
        ('/spin-async/', True),
        ('/spin/', False),
        ('/no/such/path/', False),
    ],
)
def test_a_panel_that_follows_the_view_runs_on_the_thread_of_the_view(
    path: str,
    following_on_loop: bool,
) -> None:
    recording.thread_events.clear()

    with override_settings(KALEIDOSCOPE_PANELS=PANELS_THREAD_RECORDING):
        client = AsyncClient(raise_request_exception=False)

        async_get(client, path, headers=dict(HEADERS_PAGE))

    assert recording.thread_events == [
        ('thread_recording', 'request', False),
        ('thread_following', 'request', following_on_loop),
        ('thread_following', 'response', following_on_loop),
        ('thread_recording', 'response', False),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize('path', ['/spin-async/', '/spin/'])
def test_the_profile_of_an_asgi_page_holds_the_work_of_its_view(
    toolbar_client_async: AsyncClient,
    path: str,
) -> None:
    async_get(toolbar_client_async, f'{KALEIDOSCOPE_URL_PREFIX}panels/profiling/enable/')
    async_get(toolbar_client_async, path, headers=dict(HEADERS_PAGE))

    response = async_get(toolbar_client_async, f'{KALEIDOSCOPE_URL_PREFIX}panels/profiling/data/')

    assert 'spin_for_profile' in json_read(response)['text']


@pytest.mark.django_db
def test_the_line_profile_of_an_async_view_under_asgi_times_its_lines(
    toolbar_client_async: AsyncClient,
) -> None:
    path_data = f'{KALEIDOSCOPE_URL_PREFIX}panels/line_profiling/data/'

    async_get(toolbar_client_async, f'{KALEIDOSCOPE_URL_PREFIX}panels/line_profiling/enable/')
    async_get(toolbar_client_async, '/spin-async/', headers=dict(HEADERS_PAGE))

    function = json_read(async_get(toolbar_client_async, path_data))['functions'][0]

    assert function['func_name'] == 'spin_async_view'

    assert any(
        'spin_for_profile(SPIN_MS)' in line['source'] and line['hits'] == 1
        for line in function['lines']
    )


@pytest.mark.django_db
def test_an_asgi_page_whose_panels_all_follow_the_view_never_hops_to_a_worker(
    toolbar_client_async: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _HopRecorder()

    async_get(toolbar_client_async, f'{KALEIDOSCOPE_URL_PREFIX}panels/profiling/enable/')
    monkeypatch.setattr(middleware_module, 'sync_to_async', recorder.sync_to_async)
    async_get(toolbar_client_async, '/spin-async/', headers=dict(HEADERS_PAGE))

    assert recorder.functions == []


def test_a_middleware_refuses_a_get_response_that_cannot_be_called() -> None:
    with pytest.raises(TypeError, match="get_response must be callable: 'view'"):
        KaleidoscopeMiddleware('view')  # ty:ignore[invalid-argument-type]


def test_a_middleware_refuses_something_that_is_not_a_request() -> None:
    middleware = KaleidoscopeMiddleware(_view_plain)

    with pytest.raises(TypeError, match='the middleware needs an HttpRequest, not dict'):
        middleware({})  # ty:ignore[invalid-argument-type]


def test_an_asgi_page_refuses_loop_panels_from_outside_the_active_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(middleware_module, '_panels_on_loop', _panels_on_loop_stranger)
    middleware = KaleidoscopeMiddleware(_view_plain_async)
    request = AsyncRequestFactory().get('/plain/', headers=dict(HEADERS_PAGE))

    with pytest.raises(RuntimeError, match='not among the active panels'):
        async_to_sync(middleware)(request)
