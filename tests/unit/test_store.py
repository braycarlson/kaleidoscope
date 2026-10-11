from __future__ import annotations

import contextvars
import threading

import pytest

from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import TYPE_CHECKING

from django.db import connection, connections
from django.template import Context, Engine
from django.template.base import Node, NodeList, TokenType

from kaleidoscope import store
from kaleidoscope.store import (
    STACK_FRAMES_MAX,
    TEMPLATE_FRAMES_MAX,
    CapturedRequest,
    QueryCapture,
    QueryStore,
    _dispatcher_find,
    _duplicates,
    _is_literal,
    _is_user_frame,
    _queries_listed,
    _query_record,
    _rows_counted,
    _similar_groups,
    _sql_normalized,
    _stack_listed,
    _summary,
    _template_frame,
    _templates_listed,
    _text_bounded,
    _token_text,
    user_frame_innermost,
)

from tests.testapp.models import Author, Book

if TYPE_CHECKING:
    from collections.abc import Callable


KALEIDOSCOPE_DIRECTORY = Path(store.__file__).parent.as_posix()


def _captured_request_build(
    *,
    is_ajax: bool = False,
    path: str = '/page/',
    request_id: str = 'request',
    sql_texts: tuple[str, ...] = (),
) -> CapturedRequest:
    queries = [
        {
            'alias': 'default',
            'many': False,
            'params': None,
            'raw_sql': sql,
            'rows': None,
            'sql': sql,
            'stack': (),
            'templates': (),
            'time': 0.001,
        }
        for sql in sql_texts
    ]

    return CapturedRequest(
        duration=5.0,
        is_ajax=is_ajax,
        method='GET',
        path=path,
        queries=queries,
        query_count=len(queries),
        query_time=round(len(queries) * 1.0, 2),
        request_id=request_id,
        status_code=200,
        timestamp=1.0,
    )


def _execute_fake(sql: str, params: object, many: bool, context: dict) -> str:
    _ = sql
    _ = params
    _ = many
    _ = context

    return 'executed'


def _queries_captured(run: Callable[[], object]) -> list[dict]:
    capture = QueryCapture()

    with connection.execute_wrapper(capture):
        run()

    return _queries_listed(capture.queries, stacks={}, templates={})


def _queries_captured_through(query_executed: Callable[..., object]) -> list[dict]:
    operations = SimpleNamespace(last_executed_query=query_executed)
    connection_fake = SimpleNamespace(alias='fake', ops=operations)
    context = {'connection': connection_fake, 'cursor': None}
    capture = QueryCapture()
    parameters = (1,)
    result = capture(_execute_fake, 'SELECT %s', parameters, many=False, context=context)

    assert result == 'executed'

    return capture.queries


@pytest.mark.django_db
def test_capture_records_formatted_sql_raw_sql_params_alias_and_time(library: list[Author]) -> None:
    author = library[1]
    queries = _queries_captured(lambda: Author.objects.filter(pk=author.pk).first())

    assert len(queries) == 1

    query = queries[0]

    assert query['alias'] == 'default'
    assert query['many'] is False
    assert '%s' in query['raw_sql']
    assert str(author.pk) in query['sql']
    assert '%s' not in query['sql']
    assert query['params'] == repr((author.pk,))
    assert query['time'] >= 0.0


@pytest.mark.django_db
def test_capture_stack_ends_at_the_line_that_ran_the_query(library: list[Author]) -> None:
    _ = library
    queries = _queries_captured(lambda: list(Author.objects.all()))
    frame = queries[0]['stack'][-1]

    assert frame['file'] == __file__
    assert frame['function'] == '<lambda>'
    assert 'Author.objects.all()' in frame['text']


@pytest.mark.django_db
def test_capture_stack_holds_no_frame_from_site_packages_or_kaleidoscope(
    library: list[Author],
) -> None:
    _ = library
    queries = _queries_captured(lambda: list(Author.objects.all()))

    for frame in queries[0]['stack']:
        path = frame['file'].replace('\\', '/')

        assert '/site-packages/' not in path
        assert not path.startswith(KALEIDOSCOPE_DIRECTORY + '/')


@pytest.mark.django_db
def test_capture_keeps_the_innermost_frames_when_the_stack_is_too_deep(
    monkeypatch: pytest.MonkeyPatch,
    library: list[Author],
) -> None:
    _ = library

    monkeypatch.setattr(store, 'STACK_FRAMES_MAX', 2)

    queries = _queries_captured(lambda: list(Author.objects.all()))
    stack = queries[0]['stack']

    assert len(stack) == 2
    assert stack[-1]['function'] == '<lambda>'


def test_capture_falls_back_to_raw_sql_when_formatting_answers_none() -> None:
    def query_executed(cursor: object, sql: str, params: object) -> None:
        _ = cursor
        _ = sql
        _ = params

    queries = _queries_captured_through(query_executed)

    assert queries[0]['sql'] == 'SELECT %s'
    assert queries[0]['raw_sql'] == 'SELECT %s'
    assert queries[0]['alias'] == 'fake'


def test_capture_falls_back_to_raw_sql_when_formatting_raises() -> None:
    def query_executed(cursor: object, sql: str, params: object) -> str:
        _ = cursor
        _ = sql
        _ = params
        message = 'driver lost the statement'

        raise RuntimeError(message)

    queries = _queries_captured_through(query_executed)

    assert len(queries) == 1
    assert queries[0]['sql'] == 'SELECT %s'


def test_capture_records_without_a_connection_in_the_context() -> None:
    capture = QueryCapture()
    parameters = (1,)

    capture(_execute_fake, 'SELECT %s', parameters, many=False, context={})

    assert capture.queries[0]['sql'] == 'SELECT %s'
    assert capture.queries[0]['alias'] == 'default'


@pytest.mark.django_db
def test_capture_records_a_failing_statement_and_lets_the_error_through() -> None:
    def statement_broken() -> None:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM table_that_does_not_exist')

    capture = QueryCapture()

    with connection.execute_wrapper(capture), pytest.raises(Exception, match='no such table'):
        statement_broken()

    assert len(capture.queries) == 1
    assert 'table_that_does_not_exist' in capture.queries[0]['sql']


@pytest.mark.django_db
def test_capture_stops_recording_at_the_per_request_maximum(
    monkeypatch: pytest.MonkeyPatch,
    library: list[Author],
) -> None:
    _ = library

    monkeypatch.setattr(store, 'QUERIES_PER_REQUEST_MAX', 3)

    def queries_run() -> None:
        for _ in range(5):
            list(Author.objects.all())

    queries = _queries_captured(queries_run)

    assert len(queries) == 3


@pytest.mark.django_db
def test_capture_bounds_the_parameter_and_statement_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, 'QUERY_PARAMS_LENGTH_MAX', 64)
    monkeypatch.setattr(store, 'QUERY_SQL_LENGTH_MAX', 128)

    values = tuple(range(200))
    placeholders = ', '.join(['%s'] * len(values))

    def statement_wide() -> None:
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT {placeholders}', values)

    queries = _queries_captured(statement_wide)
    query = queries[0]

    assert len(query['params']) <= 64 + len(store.TEXT_TRUNCATED_SUFFIX)
    assert query['params'].endswith(store.TEXT_TRUNCATED_SUFFIX)
    assert len(query['sql']) <= 128 + len(store.TEXT_TRUNCATED_SUFFIX)
    assert query['sql'].endswith(store.TEXT_TRUNCATED_SUFFIX)


@pytest.mark.django_db
def test_capture_survives_parameters_whose_repr_raises() -> None:
    class Unprintable:
        def __repr__(self) -> str:
            message = 'no repr for you'
            raise RuntimeError(message)

    capture = QueryCapture()
    parameters = (Unprintable(),)
    context = {'connection': connection, 'cursor': None}
    result = capture(_execute_fake, 'SELECT %s', parameters, many=False, context=context)

    assert result == 'executed'
    assert len(capture.queries) == 1
    assert 'Unprintable' in capture.queries[0]['params']


@pytest.mark.parametrize(
    ('filename', 'expected'),
    [
        ('/home/user/project/app/views.py', True),
        ('C:\\Users\\user\\project\\app\\views.py', True),
        ('/home/user/.venv/lib/python3.13/site-packages/django/db/models/query.py', False),
        ('C:\\project\\.venv\\Lib\\site-packages\\django\\db\\models\\query.py', False),
        (f'{KALEIDOSCOPE_DIRECTORY}/store.py', False),
        (f'{KALEIDOSCOPE_DIRECTORY}/panels/queries.py', False),
        (KALEIDOSCOPE_DIRECTORY.replace('/', '\\') + '\\middleware.py', False),
        (f'{KALEIDOSCOPE_DIRECTORY}-plugins/views.py', True),
        ('/usr/lib/python3/dist-packages/requests/api.py', False),
        (threading.__file__, False),
        ('<frozen runpy>', False),
        ('<string>', True),
    ],
)
def test_user_frame_excludes_site_packages_and_kaleidoscope_on_every_platform(
    filename: str,
    expected: bool,
) -> None:
    assert _is_user_frame(filename) is expected


def test_store_page_load_replaces_everything_and_ajax_appends() -> None:
    query_store = QueryStore()

    query_store.push(_captured_request_build(path='/first/'))
    query_store.push(_captured_request_build(path='/ajax-one/', is_ajax=True))
    query_store.push(_captured_request_build(path='/ajax-two/', is_ajax=True))

    paths = [request['path'] for request in query_store.data['requests']]

    assert paths == ['/first/', '/ajax-one/', '/ajax-two/']

    query_store.push(_captured_request_build(path='/second/'))

    paths = [request['path'] for request in query_store.data['requests']]

    assert paths == ['/second/']


def test_store_keeps_at_most_the_stored_maximum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, 'REQUESTS_STORED_MAX', 4)

    query_store = QueryStore()

    for index in range(10):
        captured = _captured_request_build(path=f'/ajax-{index}/', is_ajax=True)

        query_store.push(captured)

    paths = [request['path'] for request in query_store.data['requests']]

    assert paths == ['/ajax-6/', '/ajax-7/', '/ajax-8/', '/ajax-9/']
    assert query_store.summary['request_count'] == 4


def test_store_counts_exact_duplicates_and_groups_similar_statements() -> None:
    query_store = QueryStore()

    sql_texts = (
        'SELECT * FROM book WHERE id = 1',
        'SELECT * FROM book WHERE id = 1',
        'SELECT * FROM book WHERE id = 2',
        'SELECT * FROM author',
    )

    captured = _captured_request_build(sql_texts=sql_texts)

    query_store.push(captured)

    data = query_store.data

    assert data['duplicates'] == {'SELECT * FROM book WHERE id = 1': 2}
    assert len(data['similar']) == 1

    group = next(iter(data['similar'].values()))

    assert group['count'] == 3
    assert group['example'] == 'SELECT * FROM book WHERE id = 1'


def test_store_summary_agrees_with_its_data() -> None:
    query_store = QueryStore()
    page = _captured_request_build(sql_texts=('SELECT 1', 'SELECT 2'))
    ajax = _captured_request_build(sql_texts=('SELECT 3',), is_ajax=True)

    query_store.push(page)
    query_store.push(ajax)

    data = query_store.data
    summary = query_store.summary

    assert data['summary'] == summary
    assert summary['request_count'] == 2
    assert summary['total_queries'] == 3
    assert summary['total_query_time'] == 3.0


def test_store_clear_forgets_every_request() -> None:
    query_store = QueryStore()
    captured = _captured_request_build(sql_texts=('SELECT 1',))

    query_store.push(captured)
    query_store.clear()

    assert query_store.data['requests'] == []
    assert query_store.summary == {'request_count': 0, 'total_queries': 0, 'total_query_time': 0}


@pytest.mark.django_db(databases=['default', 'other'])
def test_capture_names_the_database_alias_of_each_statement() -> None:
    capture = QueryCapture()

    with (
        connections['default'].execute_wrapper(capture),
        connections['other'].execute_wrapper(capture),
        connections['default'].cursor() as default_cursor,
        connections['other'].cursor() as other_cursor,
    ):
        default_cursor.execute('SELECT 1')
        other_cursor.execute('SELECT 2')

    aliases = [query['alias'] for query in capture.queries]

    assert aliases == ['default', 'other']


@pytest.mark.parametrize(
    ('sql', 'expected'),
    [
        ('SELECT * FROM book WHERE id = 1', 'SELECT * FROM book WHERE id = %s'),
        ("SELECT * FROM book WHERE title = 'Dune'", 'SELECT * FROM book WHERE title = %s'),
        ('SELECT * FROM book WHERE price > 9.99', 'SELECT * FROM book WHERE price > %s'),
        ('SELECT  *\n FROM\tbook', 'SELECT * FROM book'),
        (
            'SELECT id FROM book WHERE id IN (1, 2, 3)',
            'SELECT id FROM book WHERE id IN (%s, %s, %s)',
        ),
        ('', ''),
        ('  SELECT 1', ' SELECT %s'),
    ],
)
def test_sql_normalized_replaces_literals_and_collapses_whitespace(sql: str, expected: str) -> None:
    assert _sql_normalized(sql) == expected


def test_sql_normalized_groups_statements_that_differ_only_by_literal() -> None:
    first = _sql_normalized('SELECT * FROM book WHERE id = 1')
    second = _sql_normalized('SELECT * FROM book WHERE id = 2')

    assert first == second


def test_sql_normalized_handles_an_in_list_past_the_sqlparse_token_limit() -> None:
    values = ', '.join(str(index) for index in range(20_000))
    normalized = _sql_normalized(f'SELECT * FROM book WHERE id IN ({values})')

    assert normalized.startswith('SELECT * FROM book WHERE id IN (%s, %s, ')
    assert normalized.count('%s') == 20_000


def test_sql_normalized_keeps_every_statement_of_a_script() -> None:
    assert _sql_normalized('SELECT 1; SELECT 2') == 'SELECT %s; SELECT %s'


def test_sql_normalized_is_idempotent() -> None:
    once = _sql_normalized("SELECT * FROM book WHERE id = 1 AND title = 'x'")

    assert _sql_normalized(once) == once


class _Ambiguous:
    def __bool__(self) -> bool:
        message = 'the truth value is ambiguous'
        raise ValueError(message)

    def __repr__(self) -> str:
        return 'Ambiguous()'


@pytest.mark.parametrize(('parameters', 'expected'), [((), None), ([], None), ({}, None)])
def test_capture_records_no_parameters_for_an_empty_collection(
    parameters: object,
    expected: str | None,
) -> None:
    capture = QueryCapture()
    context = {'connection': connection, 'cursor': None}

    capture(_execute_fake, 'SELECT 1', parameters, many=False, context=context)

    assert capture.queries[0]['params'] == expected


def test_capture_records_parameters_whose_truth_value_is_ambiguous() -> None:
    capture = QueryCapture()
    context = {'connection': connection, 'cursor': None}

    capture(_execute_fake, 'SELECT %s', _Ambiguous(), many=False, context=context)

    assert capture.queries[0]['params'] == 'Ambiguous()'


def test_capture_logs_and_skips_a_query_it_cannot_record(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(*arguments: object, **keywords: object) -> dict:
        _ = arguments
        _ = keywords
        message = 'recording is broken'

        raise RuntimeError(message)

    monkeypatch.setattr(store, '_query_record', broken)

    capture = QueryCapture()
    context = {'connection': connection, 'cursor': None}
    result = capture(_execute_fake, 'SELECT 1', None, many=False, context=context)

    assert result == 'executed'
    assert capture.queries == []
    assert 'could not record a query' in caplog.text


def test_capture_stack_stops_at_the_depth_maximum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, 'STACK_DEPTH_MAX', 1)
    monkeypatch.setattr(store, '_is_user_frame', lambda _filename: True)

    capture = QueryCapture()
    context = {'connection': connection, 'cursor': None}

    capture(_execute_fake, 'SELECT 1', None, many=False, context=context)

    queries = _queries_listed(capture.queries, stacks={}, templates={})

    assert [frame['function'] for frame in queries[0]['stack']] == ['_stack_extract']


def test_a_capture_detached_from_another_context_leaves_this_context_alone() -> None:
    capture = QueryCapture()

    capture.attach()
    contextvars.copy_context().run(capture.detach)

    assert store._capture_active.get() is capture

    capture.detach()

    assert store._capture_active.get() is None
    assert connection.execute_wrappers == []


def test_a_capture_detaches_cleanly_after_its_dispatchers_were_removed() -> None:
    capture = QueryCapture()

    capture.attach()

    for alias in connections:
        connections[alias].execute_wrappers.clear()

    capture.detach()

    assert store._capture_active.get() is None
    assert connection.execute_wrappers == []


def test_a_detached_capture_records_nothing_more() -> None:
    capture = QueryCapture()
    context = {'connection': connection, 'cursor': None}

    capture.attach()
    capture.detach()

    result = capture(_execute_fake, 'SELECT 1', None, many=False, context=context)

    assert result == 'executed'
    assert capture.queries == []


@pytest.mark.django_db
def test_captures_detached_out_of_order_record_nothing_more() -> None:
    outer = QueryCapture()
    inner = QueryCapture()

    outer.attach()
    inner.attach()
    outer.detach()
    inner.detach()

    Author.objects.count()

    assert outer.queries == []
    assert inner.queries == []
    assert connection.execute_wrappers == []


@pytest.mark.django_db
def test_capture_shares_the_connection_with_a_foreign_execute_wrapper() -> None:
    seen: list[str] = []

    def foreign(execute: Callable, sql: str, params: object, many: bool, context: dict) -> object:
        seen.append(sql)

        return execute(sql, params, many, context)

    capture = QueryCapture()

    with connection.execute_wrapper(foreign):
        capture.attach()
        Author.objects.count()
        capture.detach()

        wrappers = list(connection.execute_wrappers)

    assert len(capture.queries) == 1
    assert len(seen) == 1
    assert wrappers == [foreign]


def test_frames_refuse_a_library_directory_that_would_hide_every_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = dict.fromkeys(('platlib', 'platstdlib', 'purelib'), '/usr/lib/python3')
    paths['stdlib'] = '/'

    monkeypatch.setattr(store.sysconfig, 'get_paths', lambda: paths)
    store._frames_foreign_prefixes.cache_clear()

    try:
        with pytest.raises(RuntimeError, match='empty stdlib directory'):
            store._frames_foreign_prefixes()
    finally:
        store._frames_foreign_prefixes.cache_clear()


CAPTURED_FIELDS_VALID = MappingProxyType({
    'duration': 5.0,
    'is_ajax': False,
    'method': 'GET',
    'path': '/page/',
    'queries': [],
    'query_count': 0,
    'query_time': 0.0,
    'request_id': 'request',
    'status_code': 200,
    'timestamp': 1.0,
})


@pytest.mark.parametrize(
    ('field', 'value', 'error', 'pattern'),
    [
        ('duration', '5', TypeError, 'duration must be a number'),
        ('duration', -1.0, ValueError, 'duration must not be negative'),
        ('is_ajax', 0, TypeError, 'is_ajax must be a bool'),
        ('method', None, TypeError, 'method must be text'),
        ('method', '', ValueError, 'method must not be empty'),
        ('path', b'/page/', TypeError, 'path must be text'),
        ('queries', (), TypeError, 'queries must be a list'),
        ('query_count', 3, ValueError, 'disagrees with 0 queries'),
        ('query_time', True, TypeError, 'query_time must be a number'),
        ('query_time', -0.5, ValueError, 'query_time must not be negative'),
        ('request_id', 7, TypeError, 'request_id must be text'),
        ('request_id', '', ValueError, 'request_id must not be empty'),
        ('status_code', True, TypeError, 'status_code must be an integer, not a bool'),
        ('status_code', '200', TypeError, 'status_code must be an integer'),
        ('status_code', 99, ValueError, 'status_code must be at least 100'),
        ('status_code', 600, ValueError, 'status_code must be at most 599'),
        ('timestamp', None, TypeError, 'timestamp must be a number'),
    ],
)
def test_captured_request_refuses_a_field_of_the_wrong_kind(
    field: str,
    value: object,
    error: type[Exception],
    pattern: str,
) -> None:
    fields = {**CAPTURED_FIELDS_VALID, field: value}

    with pytest.raises(error, match=pattern):
        CapturedRequest(**fields)


def test_store_refuses_anything_but_a_captured_request() -> None:
    query_store = QueryStore()

    with pytest.raises(TypeError, match='holds captured requests, not dict'):
        query_store.push({})  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='covers captured requests, not dict'):
        _summary([{}])  # ty:ignore[invalid-argument-type]


@pytest.mark.parametrize('function', [_duplicates, _similar_groups])
def test_query_digests_refuse_queries_that_are_not_a_list(function: Callable) -> None:
    with pytest.raises(TypeError, match='queries must be a list'):
        function(())


def test_stored_queries_are_listed_only_from_tuple_stacks() -> None:
    with pytest.raises(TypeError, match='queries must be a list'):
        _queries_listed((), stacks={}, templates={})  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='stacks must be a dict'):
        _queries_listed([], stacks=[], templates={})  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='templates must be a dict'):
        _queries_listed([], stacks={}, templates=[])  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='stored stack must be a tuple of frames'):
        _queries_listed([{'stack': [], 'templates': ()}], stacks={}, templates={})

    with pytest.raises(TypeError, match='stored template stack must be a tuple of frames'):
        _queries_listed([{'stack': (), 'templates': []}], stacks={}, templates={})


def test_a_stack_longer_than_the_frame_maximum_is_refused() -> None:
    frame = ('/app/views.py', 'index', 1)
    stack = (frame,) * (STACK_FRAMES_MAX + 1)

    with pytest.raises(ValueError, match=f'at most {STACK_FRAMES_MAX} frames'):
        _stack_listed(stack)


@pytest.mark.parametrize(
    ('keywords', 'error', 'pattern'),
    [
        ({'context': None}, TypeError, 'execute context must be a dict'),
        ({'duration_ns': 1.5}, TypeError, 'duration_ns must be an integer'),
        ({'duration_ns': -1}, ValueError, 'duration_ns must not be negative'),
        ({'many': 0}, TypeError, 'many must be a bool'),
        ({'stack': []}, TypeError, 'stack must be a tuple of frames'),
        ({'templates': []}, TypeError, 'templates must be a tuple of template frames'),
    ],
)
def test_a_query_record_refuses_a_malformed_argument(
    keywords: dict,
    error: type[Exception],
    pattern: str,
) -> None:
    arguments = {
        'context': {},
        'duration_ns': 1,
        'many': False,
        'stack': (),
        'templates': (),
        **keywords,
    }

    with pytest.raises(error, match=pattern):
        _query_record('SELECT 1', None, **arguments)


def test_store_helpers_refuse_arguments_of_the_wrong_kind() -> None:
    with pytest.raises(TypeError, match='execute wrappers must be a list'):
        _dispatcher_find(())  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='token type must be a tuple'):
        _is_literal('Literal')  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='frame filename must be text'):
        _is_user_frame(7)  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='statement to normalize must be text'):
        _sql_normalized(None)  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='text to bound must be text'):
        _text_bounded(None, 10)  # ty:ignore[invalid-argument-type]

    with pytest.raises(ValueError, match='length_max must be positive'):
        _text_bounded('text', 0)


def test_a_capture_attaches_once_and_never_after_it_detached() -> None:
    capture = QueryCapture()

    capture.attach()

    with pytest.raises(RuntimeError, match='cannot attach twice'):
        capture.attach()

    capture.detach()

    with pytest.raises(RuntimeError, match='detached capture cannot attach again'):
        capture.attach()

    assert connection.execute_wrappers == []


def test_a_dispatcher_detached_more_often_than_attached_fails_loudly() -> None:
    capture = QueryCapture()

    capture.attach()

    dispatcher = _dispatcher_find(connection.execute_wrappers)

    assert dispatcher is not None

    dispatcher.depth = 0

    with pytest.raises(RuntimeError, match='detached more often than attached'):
        capture.detach()

    for alias in connections:
        connections[alias].execute_wrappers.clear()


@pytest.mark.django_db
def test_a_capture_detached_twice_leaves_a_nested_capture_attached() -> None:
    outer = QueryCapture()
    inner = QueryCapture()

    outer.attach()
    inner.attach()
    contextvars.copy_context().run(outer.detach)
    outer.detach()

    Author.objects.count()

    assert len(inner.queries) == 1

    inner.detach()

    assert connection.execute_wrappers == []


class _CursorClosed:
    @property
    def rowcount(self) -> int:
        message = 'the cursor is closed'
        raise RuntimeError(message)


class _NodeCounting(Node):
    def render(self, context: Context) -> str:
        _ = context

        return str(Book.objects.count())


def _list_engine() -> Engine:
    templates = {
        'list.html': '{% for book in books %}\n{{ book.author.name }}\n{% endfor %}',
    }

    loader = ('django.template.loaders.locmem.Loader', templates)
    loaders = [loader]

    return Engine(loaders=loaders)


@pytest.mark.parametrize(
    ('cursor', 'rows'),
    [
        (SimpleNamespace(rowcount=3), 3),
        (SimpleNamespace(rowcount=0), 0),
        (SimpleNamespace(rowcount=-1), None),
        (SimpleNamespace(rowcount=True), None),
        (SimpleNamespace(rowcount='3'), None),
        (SimpleNamespace(), None),
        (None, None),
        (_CursorClosed(), None),
    ],
)
def test_rows_are_counted_only_when_the_cursor_knows_them(cursor: object, rows: int | None) -> None:
    assert _rows_counted({'cursor': cursor}) == rows


def test_rows_refuse_a_context_that_is_not_a_dict() -> None:
    with pytest.raises(TypeError, match='execute context must be a dict'):
        _rows_counted(None)  # ty:ignore[invalid-argument-type]


@pytest.mark.django_db
def test_a_query_records_the_rows_its_statement_changed(library: list[Author]) -> None:
    _ = library

    queries = _queries_captured(lambda: Book.objects.update(title='renamed'))

    assert queries[0]['rows'] == 6


@pytest.mark.django_db
def test_a_query_issued_by_a_template_carries_the_template_lines_above_it(
    library: list[Author],
) -> None:
    _ = library

    books = list(Book.objects.order_by('pk'))
    template = _list_engine().get_template('list.html')

    queries = _queries_captured(lambda: template.render(Context({'books': books})))

    expected = [
        {'line': 1, 'name': 'list.html', 'text': '{% for book in books %}'},
        {'line': 2, 'name': 'list.html', 'text': '{{ book.author.name }}'},
    ]

    assert len(queries) == len(books)
    assert queries[0]['templates'] == expected


@pytest.mark.django_db
def test_a_query_keeps_only_the_innermost_template_lines_up_to_the_maximum(
    monkeypatch: pytest.MonkeyPatch,
    library: list[Author],
) -> None:
    _ = library

    monkeypatch.setattr(store, 'TEMPLATE_FRAMES_MAX', 1)

    books = list(Book.objects.order_by('pk'))
    template = _list_engine().get_template('list.html')

    queries = _queries_captured(lambda: template.render(Context({'books': books})))

    assert [frame['text'] for frame in queries[0]['templates']] == ['{{ book.author.name }}']


@pytest.mark.django_db
def test_a_query_from_a_node_the_parser_never_built_carries_no_template_lines() -> None:
    nodes = NodeList([_NodeCounting()])

    queries = _queries_captured(lambda: nodes.render(Context()))

    assert queries[0]['templates'] == []


@pytest.mark.django_db
def test_a_query_outside_a_template_carries_no_template_lines(library: list[Author]) -> None:
    _ = library

    queries = _queries_captured(lambda: list(Book.objects.all()))

    assert queries[0]['templates'] == []


def test_a_template_frame_needs_a_node_with_an_origin_and_a_token() -> None:
    origin = SimpleNamespace(name='/templates/page.html', template_name=None)
    token = SimpleNamespace(contents='title', lineno=None, token_type=TokenType.VAR)
    orphan = SimpleNamespace(f_locals={'self': SimpleNamespace(origin=None, token=token)})
    untokened = SimpleNamespace(f_locals={'self': SimpleNamespace(origin=origin, token=None)})
    unnumbered = SimpleNamespace(f_locals={'self': SimpleNamespace(origin=origin, token=token)})

    expected = ('/templates/page.html', 0, '{{ title }}')

    assert _template_frame(orphan) is None  # ty:ignore[invalid-argument-type]
    assert _template_frame(untokened) is None  # ty:ignore[invalid-argument-type]
    assert _template_frame(unnumbered) == expected  # ty:ignore[invalid-argument-type]


def test_token_text_wraps_a_variable_and_a_tag_in_their_delimiters() -> None:
    variable = SimpleNamespace(contents='book.title', token_type=TokenType.VAR)
    tag = SimpleNamespace(contents='if book', token_type=TokenType.BLOCK)
    text = SimpleNamespace(contents='plain', token_type=TokenType.TEXT)

    assert _token_text(variable) == '{{ book.title }}'
    assert _token_text(tag) == '{% if book %}'
    assert _token_text(text) == 'plain'


def test_a_template_stack_longer_than_the_frame_maximum_is_refused() -> None:
    frame = ('page.html', 1, '{{ title }}')
    templates = (frame,) * (TEMPLATE_FRAMES_MAX + 1)

    with pytest.raises(ValueError, match=f'holds {TEMPLATE_FRAMES_MAX + 1} frames'):
        _templates_listed(templates)


def test_store_finds_a_request_by_its_id() -> None:
    query_store = QueryStore()
    first = _captured_request_build(path='/first/', request_id='first')
    second = _captured_request_build(is_ajax=True, path='/second/', request_id='second')

    query_store.push(first)
    query_store.push(second)

    assert query_store.request_find('second') is second
    assert query_store.request_find('missing') is None


def test_store_refuses_a_request_id_that_is_not_text() -> None:
    with pytest.raises(TypeError, match='request_id must be text'):
        QueryStore().request_find(7)  # ty:ignore[invalid-argument-type]


def test_the_innermost_user_frame_is_the_code_that_asked() -> None:
    frame = user_frame_innermost()

    assert frame is not None
    assert frame['file'] == __file__
    assert frame['function'] == 'test_the_innermost_user_frame_is_the_code_that_asked'


def test_no_user_frame_is_found_on_a_stack_of_library_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store, '_is_user_frame', lambda _filename: False)

    assert user_frame_innermost() is None
