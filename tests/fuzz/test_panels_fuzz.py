from __future__ import annotations

import json
import re

import pytest

from hypothesis import example, given
from hypothesis import strategies as st

from django.core.cache import cache
from django.test import Client
from django.views.debug import SafeExceptionReporterFilter

from kaleidoscope import store as store_module
from kaleidoscope.panels.cache import FORMAT_ARGS_LENGTH_MAX, _arguments_text
from kaleidoscope.panels.line_profiling import PATH_LENGTH_MAX, _path_shortened
from kaleidoscope.panels.request import _url_path_shortened
from kaleidoscope.panels.settings import MASKED_VALUE, _setting_serialized
from kaleidoscope.panels.static_files import _static_paths_used
from kaleidoscope.store import CapturedRequest, QueryStore, _sql_normalized

from tests.fuzz.settings import fuzz_settings
from tests.fuzz.strategies import (
    HTML_DOCUMENTS,
    SQL_STATEMENTS,
    TEXT_CHARACTERS,
    TEXTS_ANY,
    TEXTS_HOSTILE,
    VALUES_NESTED,
    json_strict_load,
)
from tests.simulation.oracle import cache_call_expected
from tests.testapp.work import CacheOperation, WorkPlan
from tests.toolbar import panel_data


pytestmark = pytest.mark.fuzz
CACHE_KEYS = ('alpha', 'beta', 'gamma')
CACHE_OPERATION_CLEAR = CacheOperation(name='clear')
CANARY = 'canary-fuzzed-secret'
LITERAL_CHARACTERS_UNAMBIGUOUS = st.characters(exclude_categories=('Cs',), exclude_characters='\\')
NOISE_KEYS = st.text(alphabet='abcdefghij', min_size=1, max_size=6)
SECRET_PREFIXES = ('', 'DB_', 'aws_', 'Service')
SECRET_SUFFIXES = ('', '_VALUE', '2')
STATEMENTS = ('SELECT 1', 'SELECT 2', 'SELECT 3')
STATIC_TERMINATORS = '"\'?#) \n\r>'
STATIC_URLS = ('/static/', 'static/', 'https://cdn.x/s/', '/', 'x')

LITERALS_UNAMBIGUOUS = st.one_of(
    st.integers(min_value=0, max_value=10**15).map(str),
    st.text(alphabet=LITERAL_CHARACTERS_UNAMBIGUOUS, max_size=12).map(
        lambda text: "'" + text.replace("'", "''") + "'",
    ),
)

SECRET_WORDS = (
    'API_KEY',
    'passphrase',
    'PASSWD',
    'Password',
    'private_key',
    'SECRET',
    'Signature',
    'token',
)

SECRET_NAMES = st.builds(
    '{}{}{}'.format,
    st.sampled_from(SECRET_PREFIXES),
    st.sampled_from(SECRET_WORDS),
    st.sampled_from(SECRET_SUFFIXES),
)

CACHE_OPERATIONS = st.one_of(
    st.builds(
        CacheOperation,
        name=st.sampled_from(['add', 'del', 'get', 'getd', 'gos', 'has', 'set']),
        keys=st.sampled_from(CACHE_KEYS).map(lambda key: (key,)),
    ),
    st.builds(
        CacheOperation,
        name=st.just('many'),
        keys=st.lists(st.sampled_from(CACHE_KEYS), min_size=1, max_size=3, unique=True).map(tuple),
    ),
    st.just(CACHE_OPERATION_CLEAR),
)


def _secret_nested(depth: int, name: str) -> object:
    value: object = {name: CANARY, 'visible': 'shown'}

    for index in range(depth):
        value = [value] if index % 2 else {'level': value}

    return value


@fuzz_settings
@given(operations=st.lists(CACHE_OPERATIONS, max_size=12))
@pytest.mark.django_db
def test_cache_panel_reports_each_call_and_its_hit_like_a_model(
    operations: list[CacheOperation],
) -> None:
    cache.clear()

    client = Client(raise_request_exception=True)
    plan = WorkPlan(cache_operations=tuple(operations), kind='json')
    present: set[str] = set()
    expected = [cache_call_expected(operation, present) for operation in operations]

    client.get(f'/work/?{plan.query_string()}')

    calls = panel_data(client, 'cache')['calls']

    assert [(call['method'], call['hit']) for call in calls] == expected


@fuzz_settings
@given(
    arguments=st.lists(VALUES_NESTED, max_size=4),
    keywords=st.dictionaries(st.text(max_size=8), VALUES_NESTED, max_size=3),
)
def test_cache_arguments_are_formatted_within_their_bound(arguments: list, keywords: dict) -> None:
    text = _arguments_text(tuple(arguments), keywords)

    assert len(text) <= FORMAT_ARGS_LENGTH_MAX + len('...')


def _static_references(content: str, static_url: str | None) -> list[str]:
    if not static_url:
        return []

    pattern = re.escape(static_url) + '([^' + re.escape(STATIC_TERMINATORS) + ']*)'

    return sorted({path for path in re.findall(pattern, content) if path})


@fuzz_settings
@given(
    depth=st.integers(min_value=0, max_value=8),
    name=SECRET_NAMES,
    noise=st.dictionaries(NOISE_KEYS, VALUES_NESTED, max_size=3),
)
@example(depth=0, name='DB_PASSWD', noise={})
@example(depth=1, name='ssh_passphrase', noise={})
def test_settings_never_show_a_secret_at_any_depth(depth: int, name: str, noise: dict) -> None:
    value = {'nested': _secret_nested(depth, name), **noise}
    shown = _setting_serialized('SERVICE', value)
    text = json.dumps(shown, allow_nan=False)

    assert SafeExceptionReporterFilter.hidden_settings.search(name)
    assert CANARY not in text
    assert MASKED_VALUE in text
    assert isinstance(json_strict_load(text), dict | list | str)


@fuzz_settings
@given(
    entries=st.lists(
        st.tuples(st.booleans(), st.lists(st.sampled_from(STATEMENTS), max_size=4)),
        max_size=30,
    ),
    stored_max=st.integers(min_value=1, max_value=8),
)
def test_query_store_matches_a_reference_model(
    monkeypatch: pytest.MonkeyPatch,
    entries: list[tuple[bool, list[str]]],
    stored_max: int,
) -> None:
    monkeypatch.setattr(store_module, 'REQUESTS_STORED_MAX', stored_max)

    query_store = QueryStore()
    model: list[list[str]] = []

    for index, (is_ajax, sql_texts) in enumerate(entries):
        queries = [
            {
                'alias': 'default',
                'raw_sql': sql,
                'rows': None,
                'sql': sql,
                'stack': (),
                'templates': (),
                'time': 0.001,
            }
            for sql in sql_texts
        ]

        captured = CapturedRequest(
            duration=1.0,
            is_ajax=is_ajax,
            method='GET',
            path=f'/{index}/',
            queries=queries,
            query_count=len(queries),
            query_time=float(len(queries)),
            request_id=f'request-{index}',
            status_code=200,
            timestamp=float(index),
        )

        query_store.push(captured)

        if not is_ajax:
            model.clear()

        model.append(sql_texts)
        del model[:-stored_max]

    data = query_store.data
    flattened = [sql for sql_texts in model for sql in sql_texts]
    duplicates = {sql: flattened.count(sql) for sql in set(flattened) if flattened.count(sql) > 1}
    counts = [len(request['queries']) for request in data['requests']]

    assert counts == [len(item) for item in model]
    assert data['summary']['request_count'] == len(model)
    assert data['summary']['total_queries'] == len(flattened)
    assert data['duplicates'] == duplicates
    assert len(data['requests']) <= stored_max


@fuzz_settings
@given(header_value=TEXTS_HOSTILE)
@pytest.mark.django_db
def test_request_panel_data_is_always_strict_json(header_value: str) -> None:
    client = Client(raise_request_exception=True)

    client.get('/plain/', headers={'X-Custom': header_value})

    response = client.get('/__kaleidoscope__/panels/request/data/')

    assert response.status_code == 200
    json_strict_load(response.content)


@fuzz_settings
@given(sql=st.one_of(SQL_STATEMENTS, TEXTS_ANY))
@example(sql='SELECT * FROM book WHERE id IN (' + ', '.join(['1'] * 20_000) + ')')
@example(sql='\x00')
def test_sql_normalized_answers_the_same_text_for_any_input(sql: str) -> None:
    normalized = _sql_normalized(sql)

    assert isinstance(normalized, str)
    assert _sql_normalized(sql) == normalized


@fuzz_settings
@given(
    first=st.lists(LITERALS_UNAMBIGUOUS, min_size=3, max_size=3),
    second=st.lists(LITERALS_UNAMBIGUOUS, min_size=3, max_size=3),
)
def test_sql_normalized_groups_statements_that_differ_only_by_literals(
    first: list[str],
    second: list[str],
) -> None:
    template = 'SELECT * FROM "book" WHERE "book"."id" = {} AND "book"."title" = {} LIMIT {}'

    assert _sql_normalized(template.format(*first)) == _sql_normalized(template.format(*second))


@fuzz_settings
@given(
    path=st.text(alphabet=TEXT_CHARACTERS, max_size=200),
    length_max=st.integers(min_value=4, max_value=120),
)
def test_path_shortening_never_lengthens_and_never_raises(path: str, length_max: int) -> None:
    assert len(_path_shortened(path)) <= max(PATH_LENGTH_MAX, len(path))
    assert len(_url_path_shortened(path, length_max)) <= max(length_max, len(path))


@fuzz_settings
@given(
    content=st.one_of(HTML_DOCUMENTS, TEXTS_ANY),
    static_url=st.one_of(st.none(), st.sampled_from(STATIC_URLS)),
)
@example(content='<script src="/static/vendor/static/app.js">', static_url='/static/')
def test_static_paths_used_finds_each_reference_once_and_whole(
    content: str,
    static_url: str | None,
) -> None:
    used = _static_paths_used(content, static_url or '')

    assert used == _static_references(content, static_url)
