from __future__ import annotations

import contextvars
import json

import pytest

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.db import connection, connections
from django.http import HttpResponse

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.middleware import KaleidoscopeMiddleware
from kaleidoscope.panels import queries as queries_panel
from kaleidoscope.panels.queries import (
    EXPLAIN_REQUEST_ID_LENGTH_MAX,
    QueriesPanel,
    _explain_line,
    _query_time_ms,
    _statement_kind,
)
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX
from kaleidoscope.store import QUERY_SQL_LENGTH_MAX, CapturedRequest, QueryCapture

from tests.testapp.models import Author
from tests.toolbar import HEADERS_AJAX, json_read, panel_data, panels_listed

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.test import Client, RequestFactory


@pytest.mark.django_db
def test_queries_panel_counts_an_n_plus_one_page(
    toolbar_client: Client,
    library: list[Author],
) -> None:
    toolbar_client.get('/page/')

    data = panel_data(toolbar_client, 'queries')
    request = data['requests'][0]
    similar = list(data['similar'].values())

    assert request['query_count'] == 1 + len(library)
    assert request['method'] == 'GET'
    assert request['path'] == '/page/'
    assert request['status_code'] == 200
    assert request['is_ajax'] is False
    assert len(similar) == 1
    assert similar[0]['count'] == len(library)


@pytest.mark.django_db
def test_queries_panel_counts_exact_duplicates(
    toolbar_client: Client,
    library: list[Author],
) -> None:
    _ = library

    toolbar_client.get('/work/?queries=6&distinct=2')

    duplicates = panel_data(toolbar_client, 'queries')['duplicates']

    assert sorted(duplicates.values()) == [3, 3]


@pytest.mark.django_db
def test_queries_panel_records_the_status_of_a_failing_view(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?queries=2&fail=1')

    request = panel_data(toolbar_client, 'queries')['requests'][0]

    assert request['status_code'] == 500
    assert request['query_count'] == 2


@pytest.mark.django_db
def test_queries_panel_data_survives_a_huge_in_list(request_factory: RequestFactory) -> None:
    def get_response(request: HttpRequest) -> HttpResponse:
        _ = request
        identifiers = list(range(12_000))

        list(Author.objects.filter(pk__in=identifiers))

        return HttpResponse('<html><body>huge</body></html>')

    middleware = KaleidoscopeMiddleware(get_response)
    request = request_factory.get('/huge/')

    middleware(request)

    panel = middleware._registry.panels['queries']
    data = panel.get_data()

    assert isinstance(panel, QueriesPanel)
    assert data['summary']['total_queries'] == 1
    assert data['similar'] == {}


@pytest.mark.django_db(databases=['default', 'other'])
def test_queries_panel_captures_every_database_alias(request_factory: RequestFactory) -> None:
    def get_response(request: HttpRequest) -> HttpResponse:
        _ = request

        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')

        with connections['other'].cursor() as cursor:
            cursor.execute('SELECT 2')

        return HttpResponse('<html><body>both</body></html>')

    middleware = KaleidoscopeMiddleware(get_response)
    request = request_factory.get('/both/')

    middleware(request)

    queries = middleware._registry.panels['queries'].get_data()['requests'][0]['queries']

    assert [query['alias'] for query in queries] == ['default', 'other']

    for alias in connections:
        assert connections[alias].execute_wrappers == []


@pytest.mark.django_db
def test_queries_panel_summary_counts_queries_and_time(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?queries=3')
    toolbar_client.get('/work/?queries=2', headers=HEADERS_AJAX)

    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}

    assert summaries['queries'].startswith('5 queries, ')


def test_queries_panel_summary_is_zero_before_any_request(toolbar_client: Client) -> None:
    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}

    assert summaries['queries'] == '0 queries'


@pytest.mark.django_db
def test_queries_panel_leaves_no_wrapper_after_a_request(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?queries=3')
    toolbar_client.get('/work/?queries=3&fail=1')

    assert connection.execute_wrappers == []


def _statement_run(text: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute('SELECT %s', [text])


@pytest.mark.django_db
def test_captures_in_separate_contexts_share_one_wrapper_and_keep_their_statements() -> None:
    first = QueryCapture()
    second = QueryCapture()
    context_first = contextvars.copy_context()
    context_second = contextvars.copy_context()

    context_first.run(first.attach)
    context_second.run(second.attach)
    context_second.run(_statement_run, 'second')
    context_first.run(_statement_run, 'first')
    _statement_run('outside')

    assert len(connection.execute_wrappers) == 1

    context_first.run(first.detach)

    assert len(connection.execute_wrappers) == 1

    context_second.run(second.detach)

    assert connection.execute_wrappers == []
    assert [query['sql'] for query in first.queries] == ["SELECT 'first'"]
    assert [query['sql'] for query in second.queries] == ["SELECT 'second'"]


@pytest.mark.django_db
def test_a_nested_capture_hands_statements_back_to_the_outer_one() -> None:
    outer = QueryCapture()
    inner = QueryCapture()

    outer.attach()
    inner.attach()
    _statement_run('inner')
    inner.detach()
    _statement_run('outer')
    outer.detach()

    assert connection.execute_wrappers == []
    assert [query['sql'] for query in inner.queries] == ["SELECT 'inner'"]
    assert [query['sql'] for query in outer.queries] == ["SELECT 'outer'"]


def test_query_time_refuses_queries_that_are_no_list_or_took_negative_time() -> None:
    queries_tuple = ()
    queries = [{'time': -1.0}]

    with pytest.raises(TypeError, match='queries must be a list, not tuple'):
        _query_time_ms(queries_tuple)  # ty:ignore[invalid-argument-type]

    with pytest.raises(RuntimeError, match='the queries took a negative time'):
        _query_time_ms(queries)


def test_queries_panel_refuses_a_capture_over_the_per_request_maximum(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    monkeypatch.setattr(queries_panel, 'QUERIES_PER_REQUEST_MAX', 1)

    panel = QueriesPanel()
    capture = QueryCapture()
    capture.queries = [{'time': 0.001}, {'time': 0.002}]
    context = KaleidoscopeContext(state={'queries': capture})
    request = request_factory.get('/')
    response = HttpResponse()

    with pytest.raises(RuntimeError, match='the capture holds 2 queries, over 1'):
        panel.process_response(request, response, context)

    assert panel.store.summary['request_count'] == 0


def _explain_answer(panel: QueriesPanel, request_factory: RequestFactory, query: str) -> tuple:
    request = request_factory.get(f'/?{query}')
    response = panel.handle_action('explain', request)

    if response is None:
        message = 'the explain action answered nothing'
        raise AssertionError(message)

    return response.status_code, json.loads(response.content)


def _explain_get(client: Client, *, query_index: int, request_id: str) -> HttpResponse:
    query = urlencode({'query': query_index, 'request': request_id})

    return client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/action/explain/?{query}')


def _panel_holding(**fields: object) -> QueriesPanel:
    query = {
        'alias': 'default',
        'many': False,
        'params': None,
        'raw_sql': 'SELECT 1',
        'rows': None,
        'sql': 'SELECT 1',
        'stack': (),
        'templates': (),
        'time': 0.001,
        **fields,
    }

    queries = [query]
    panel = QueriesPanel()

    captured = CapturedRequest(
        duration=1.0,
        is_ajax=False,
        method='GET',
        path='/held/',
        queries=queries,
        query_count=len(queries),
        query_time=1.0,
        request_id='held',
        status_code=200,
        timestamp=1.0,
    )

    panel.store.push(captured)

    return panel


@pytest.mark.django_db
def test_explain_shows_the_plan_of_a_captured_select(
    toolbar_client: Client,
    library: list[Author],
) -> None:
    _ = library

    toolbar_client.get('/page/')

    request = panel_data(toolbar_client, 'queries')['requests'][0]
    response = _explain_get(toolbar_client, query_index=0, request_id=request['request_id'])
    body = json_read(response)

    assert response.status_code == 200
    assert body['command'] == 'EXPLAIN QUERY PLAN'
    assert 'testapp_author' in body['plan']


@pytest.mark.django_db
def test_explain_runs_a_parameterized_select_with_its_parameters_filled_in(
    toolbar_client: Client,
    library: list[Author],
) -> None:
    _ = library

    toolbar_client.get('/work/?queries=1')

    request = panel_data(toolbar_client, 'queries')['requests'][0]
    query = request['queries'][0]
    response = _explain_get(toolbar_client, query_index=0, request_id=request['request_id'])

    assert query['params'] is not None
    assert response.status_code == 200
    assert 'testapp_author' in json_read(response)['plan']


@pytest.mark.django_db
def test_explain_asks_postgresql_to_analyze_and_count_buffers(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    options_seen: list[dict] = []

    def prefix(**options: object) -> str:
        options_seen.append(options)

        return 'EXPLAIN'

    database = connections['default']

    monkeypatch.setattr(database, 'vendor', 'postgresql')
    monkeypatch.setattr(database.ops, 'explain_query_prefix', prefix)

    panel = _panel_holding()
    status, body = _explain_answer(panel, request_factory, 'request=held&query=0')

    assert status == 200
    assert body['command'] == 'EXPLAIN'
    assert options_seen == [{'analyze': True, 'buffers': True}]


@pytest.mark.parametrize(
    ('query', 'status', 'error'),
    [
        ('query=0', 400, 'invalid params'),
        (f'request={"x" * (EXPLAIN_REQUEST_ID_LENGTH_MAX + 1)}&query=0', 400, 'invalid params'),
        ('request=held&query=first', 400, 'invalid params'),
        ('request=missing&query=0', 404, 'request not found'),
        ('request=held&query=-1', 404, 'query not found'),
        ('request=held&query=1', 404, 'query not found'),
    ],
)
def test_explain_refuses_a_request_or_query_it_cannot_find(
    request_factory: RequestFactory,
    query: str,
    status: int,
    error: str,
) -> None:
    panel = _panel_holding()

    assert _explain_answer(panel, request_factory, query) == (status, {'error': error})


@pytest.mark.parametrize(
    ('fields', 'error'),
    [
        ({'many': True}, 'an executemany statement cannot be explained'),
        ({'raw_sql': 'UPDATE testapp_author SET name = %s'}, 'only a SELECT can be explained'),
        ({'sql': 'SELECT ' + 'x' * QUERY_SQL_LENGTH_MAX}, 'too long to capture whole'),
        ({'params': '(1,)', 'raw_sql': 'SELECT %s', 'sql': 'SELECT %s'}, 'without its parameters'),
        ({'alias': 'removed'}, "the database 'removed' is not configured"),
    ],
)
def test_explain_refuses_a_statement_it_cannot_run_safely(
    request_factory: RequestFactory,
    fields: dict,
    error: str,
) -> None:
    panel = _panel_holding(**fields)
    status, body = _explain_answer(panel, request_factory, 'request=held&query=0')

    assert status == 400
    assert error in body['error']


@pytest.mark.django_db
def test_explain_reports_the_error_of_a_statement_the_database_refuses(
    request_factory: RequestFactory,
) -> None:
    sql = 'SELECT name FROM missing_table'
    panel = _panel_holding(raw_sql=sql, sql=sql)
    status, body = _explain_answer(panel, request_factory, 'request=held&query=0')

    assert status == 400
    assert 'missing_table' in body['error']


def test_explain_refuses_something_that_is_not_a_request() -> None:
    with pytest.raises(TypeError, match='needs an HttpRequest, not NoneType'):
        QueriesPanel().handle_action('explain', None)  # ty:ignore[invalid-argument-type]


def test_statement_kind_names_the_first_keyword_or_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _statement_kind('SELECT 1') == 'SELECT'
    assert _statement_kind('UPDATE a SET b = 1') == 'UPDATE'
    assert _statement_kind('') == 'UNKNOWN'

    def parse_broken(sql: str) -> tuple:
        _ = sql
        message = 'the parser gave up'

        raise RuntimeError(message)

    monkeypatch.setattr(queries_panel.sqlparse, 'parse', parse_broken)

    assert _statement_kind('SELECT 1') == 'UNKNOWN'


def test_explain_lines_join_the_columns_of_a_row() -> None:
    assert _explain_line(('Seq Scan on book',)) == 'Seq Scan on book'
    assert _explain_line((2, 0, 0, 'SCAN book')) == '2 0 0 SCAN book'
