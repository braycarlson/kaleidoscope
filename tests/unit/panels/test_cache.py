from __future__ import annotations

import pytest

from types import SimpleNamespace
from typing import TYPE_CHECKING

from django.core.cache import cache, caches
from django.http import HttpResponse

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panels import cache as cache_panel
from kaleidoscope.panels.cache import (
    FORMAT_ARGS_LENGTH_MAX,
    CacheMethod,
    CachePanel,
    _arguments_text,
    _cache_patch,
    _caches_unpatch,
    _call_record,
    _call_tracked,
    _hit_resolve,
    _hits_misses,
    _is_weakly_referable,
    _wrapper_build,
)

from tests.toolbar import HEADERS_AJAX, panel_data, panel_toggle, panels_listed

if TYPE_CHECKING:
    from django.test import Client, RequestFactory


class _CachePatchedConcurrently:
    def __init__(self) -> None:
        self.checks = 0

    @property
    def _kaleidoscope_patched(self) -> bool:
        self.checks += 1

        return self.checks > 1

    def get(self, key: str) -> None:
        _ = key


def _calls_recorded(toolbar_client: Client, operations: str) -> list[tuple[str, bool]]:
    toolbar_client.get(f'/work/?cache={operations}')

    calls = panel_data(toolbar_client, 'cache')['calls']

    return [(call['method'], call['hit']) for call in calls]


@pytest.mark.django_db
def test_get_reports_a_miss_then_a_hit(toolbar_client: Client) -> None:
    recorded = _calls_recorded(toolbar_client, 'get:alpha,set:alpha,get:alpha')

    assert recorded == [('GET', False), ('SET', False), ('GET', True)]


@pytest.mark.django_db
def test_get_with_a_default_reports_a_miss_when_the_key_is_absent(toolbar_client: Client) -> None:
    recorded = _calls_recorded(toolbar_client, 'getd:alpha,set:alpha,getd:alpha')

    assert recorded == [('GET', False), ('SET', False), ('GET', True)]


@pytest.mark.django_db
def test_get_reports_a_hit_on_a_cached_value_equal_to_the_default(toolbar_client: Client) -> None:
    toolbar_client.get('/plain/')

    cache_panel._collecting.set([])
    cache.set('flag', value=False)
    found = cache.get('flag', False)
    missing = cache.get('absent', False)
    calls = cache_panel._collecting.get()

    cache_panel._collecting.set(None)

    assert found is False
    assert missing is False

    assert [(call['method'], call['hit']) for call in calls] == [
        ('SET', False),
        ('GET', True),
        ('GET', False),
    ]


@pytest.mark.django_db
def test_has_key_reports_a_miss_when_the_key_is_absent(toolbar_client: Client) -> None:
    recorded = _calls_recorded(toolbar_client, 'has:alpha,set:alpha,has:alpha')

    assert recorded == [('HAS_KEY', False), ('SET', False), ('HAS_KEY', True)]


@pytest.mark.django_db
def test_get_or_set_is_one_call_that_misses_then_hits(toolbar_client: Client) -> None:
    recorded = _calls_recorded(toolbar_client, 'gos:alpha,gos:alpha')

    assert recorded == [('GET_OR_SET', False), ('GET_OR_SET', True)]


@pytest.mark.django_db
def test_get_many_is_one_call_that_hits_only_when_every_key_is_found(
    toolbar_client: Client,
) -> None:
    recorded = _calls_recorded(toolbar_client, 'set:alpha,many:alpha.beta,set:beta,many:alpha.beta')

    assert recorded == [('SET', False), ('GET_MANY', False), ('SET', False), ('GET_MANY', True)]


@pytest.mark.django_db
def test_writes_never_count_as_hits(toolbar_client: Client) -> None:
    recorded = _calls_recorded(toolbar_client, 'add:alpha,add:alpha,incr:alpha,del:alpha,clear')

    assert recorded == [
        ('ADD', False),
        ('ADD', False),
        ('INCR', False),
        ('DELETE', False),
        ('CLEAR', False),
    ]


@pytest.mark.django_db
def test_hits_and_misses_are_summed_over_reads_only(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?cache=get:alpha,set:alpha,get:alpha,has:beta,del:alpha')

    data = panel_data(toolbar_client, 'cache')
    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}

    assert data['count'] == 5
    assert data['hits'] == 1
    assert data['misses'] == 2
    assert summaries['cache'] == '5 calls, 1 hits, 2 misses'


@pytest.mark.django_db
def test_a_page_load_replaces_the_calls_and_ajax_appends(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?cache=set:alpha')
    toolbar_client.get('/work/?cache=get:alpha', headers=HEADERS_AJAX)

    methods = [call['method'] for call in panel_data(toolbar_client, 'cache')['calls']]

    assert methods == ['SET', 'GET']

    toolbar_client.get('/work/?cache=del:alpha')

    methods = [call['method'] for call in panel_data(toolbar_client, 'cache')['calls']]

    assert methods == ['DELETE']


@pytest.mark.django_db
def test_ajax_calls_accumulate_only_up_to_the_maximum(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
) -> None:
    monkeypatch.setattr(cache_panel, 'CACHE_CALLS_MAX', 5)

    toolbar_client.get('/plain/')

    for _ in range(4):
        toolbar_client.get('/work/?cache=get:alpha,get:beta', headers=HEADERS_AJAX)

    assert panel_data(toolbar_client, 'cache')['count'] == 5


@pytest.mark.django_db
def test_a_failing_cache_call_is_recorded_and_still_raises(toolbar_client: Client) -> None:
    response = toolbar_client.get('/work/?cache=incr:missing')

    assert response.status_code == 500

    calls = panel_data(toolbar_client, 'cache')['calls']

    assert [(call['method'], call['hit']) for call in calls] == [('INCR', False)]


def test_arguments_text_survives_an_argument_whose_repr_raises() -> None:
    class Unprintable:
        def __repr__(self) -> str:
            message = 'no repr for you'
            raise RuntimeError(message)

    arguments = (Unprintable(),)
    keywords = {'version': Unprintable()}
    text = _arguments_text(arguments, keywords)

    assert 'Unprintable' in text
    assert 'version=' in text


def test_arguments_text_is_bounded_for_a_huge_argument() -> None:
    arguments = ('k' * 10_000, list(range(10_000)))
    text = _arguments_text(arguments, {})

    assert len(text) <= FORMAT_ARGS_LENGTH_MAX + len('...')


def test_cache_panel_summary_is_zero_before_any_call() -> None:
    assert CachePanel().get_summary() == '0 calls'


@pytest.mark.django_db
def test_cache_calls_outside_a_request_are_never_recorded(toolbar_client: Client) -> None:
    toolbar_client.get('/plain/')

    cache.set('outside', 1)
    cache.get('outside')

    assert panel_data(toolbar_client, 'cache')['calls'] == []


@pytest.mark.django_db
def test_cache_calls_stop_recording_at_the_per_request_maximum(
    monkeypatch: pytest.MonkeyPatch,
    toolbar_client: Client,
) -> None:
    monkeypatch.setattr(cache_panel, 'CACHE_CALLS_MAX', 2)

    recorded = _calls_recorded(toolbar_client, 'get:alpha,get:beta,get:gamma')

    assert recorded == [('GET', False), ('GET', False)]


def test_a_cache_patched_by_another_thread_meanwhile_is_left_alone() -> None:
    backend = _CachePatchedConcurrently()
    get_original = backend.get

    _cache_patch(backend, 'racing')

    assert backend.get == get_original
    assert backend.checks == 2


def test_a_cache_backend_missing_methods_is_patched_where_it_can_be() -> None:
    def get(key: str) -> None:
        _ = key

    backend = SimpleNamespace(get=get)

    _cache_patch(backend, 'partial')

    assert backend.get is not get
    assert backend.get.__wrapped__ is get
    assert not hasattr(backend, 'set')
    assert backend._kaleidoscope_patched is True


@pytest.mark.parametrize(('found', 'hit'), [({'alpha': 1}, True), ({}, False)])
def test_get_many_with_keys_of_unknown_length_hits_when_anything_is_found(
    found: dict,
    hit: bool,
) -> None:
    keys = iter(['alpha'])
    arguments = (keys,)
    method = CacheMethod.GET_MANY

    assert _hit_resolve(method, args=arguments, kwargs={}, nested=[], result=found) is hit


@pytest.mark.django_db
def test_cache_summary_counts_writes_that_neither_hit_nor_miss(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?cache=set:alpha,del:alpha')

    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}

    assert summaries['cache'] == '2 calls'


class _CacheBackend:
    def get(self, key: str) -> None:
        _ = key

    def set(self, key: str, value: object) -> None:
        _ = key
        _ = value


def test_unpatching_restores_the_methods_of_every_patched_cache() -> None:
    backend = _CacheBackend()

    _cache_patch(backend, 'tracked')

    assert 'get' in vars(backend)

    _caches_unpatch()

    assert vars(backend) == {}
    assert backend.get.__func__ is _CacheBackend.get


def test_a_cache_without_weak_references_is_patched_but_never_tracked() -> None:
    assert _is_weakly_referable(_CacheBackend()) is True
    assert _is_weakly_referable(SimpleNamespace()) is False


@pytest.mark.django_db
def test_isolation_removes_the_cache_wrappers_until_it_ends(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?cache=get:alpha')
    backend = caches['default']

    assert 'get' in vars(backend)

    panel_toggle(toolbar_client, 'profiling', enabled=True)
    toolbar_client.get('/work/?cache=get:alpha')

    assert 'get' not in vars(backend)
    assert not hasattr(backend, '_kaleidoscope_patched')

    panel_toggle(toolbar_client, 'profiling', enabled=False)
    toolbar_client.get('/work/?cache=get:alpha')

    assert 'get' in vars(backend)


def _record(**overrides: object) -> None:
    calls: list = []

    arguments = {
        'alias': 'default',
        'args': (),
        'duration_ns': 0,
        'hit': False,
        'kwargs': {},
        'method': CacheMethod.GET,
    }

    arguments.update(overrides)

    _call_record(calls, **arguments)  # ty:ignore[invalid-argument-type]


def test_arguments_text_refuses_arguments_that_are_not_a_tuple_and_a_dict() -> None:
    arguments = ['key']
    keywords: dict = {}

    with pytest.raises(TypeError, match='args must be a tuple, not list'):
        _arguments_text(arguments, keywords)  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='kwargs must be a dict, not list'):
        _arguments_text((), arguments)  # ty:ignore[invalid-argument-type]


@pytest.mark.parametrize(
    ('overrides', 'error', 'pattern'),
    [
        ({'method': 'get'}, TypeError, "method must be a CacheMethod: 'get'"),
        ({'hit': 1}, TypeError, 'hit must be a bool: 1'),
        ({'duration_ns': -1}, ValueError, 'duration_ns must not be negative: -1'),
    ],
)
def test_a_call_record_refuses_a_field_of_the_wrong_kind(
    overrides: dict,
    error: type[Exception],
    pattern: str,
) -> None:
    with pytest.raises(error, match=pattern):
        _record(**overrides)


def test_a_tracked_call_refuses_an_uncallable_original_or_a_collector_that_is_no_list() -> None:
    calls: list = []
    collector = ()
    keywords: dict = {}
    method = CacheMethod.SET

    with pytest.raises(TypeError, match='original must be callable, not str'):
        _call_tracked(
            'set',  # ty:ignore[invalid-argument-type]
            alias='default',
            args=(),
            calls=calls,
            kwargs=keywords,
            method=method,
        )

    with pytest.raises(TypeError, match='calls must be a list, not tuple'):
        _call_tracked(
            len,
            alias='default',
            args=(),
            calls=collector,  # ty:ignore[invalid-argument-type]
            kwargs=keywords,
            method=method,
        )


@pytest.mark.parametrize(
    ('alias', 'error', 'pattern'),
    [(7, TypeError, 'a cache alias must be text: 7'), ('', ValueError, 'must not be empty')],
)
def test_patching_refuses_an_alias_that_is_no_name(
    alias: object,
    error: type[Exception],
    pattern: str,
) -> None:
    backend = _CacheBackend()

    with pytest.raises(error, match=pattern):
        _cache_patch(backend, alias)  # ty:ignore[invalid-argument-type]

    assert vars(backend) == {}


def test_hit_resolution_refuses_a_method_or_a_nesting_of_the_wrong_kind() -> None:
    arguments = ('alpha',)
    keywords: dict = {}
    nested: list = []
    nesting = ()

    with pytest.raises(TypeError, match="method must be a CacheMethod: 'get'"):
        _hit_resolve(
            'get',  # ty:ignore[invalid-argument-type]
            args=arguments,
            kwargs=keywords,
            nested=nested,
            result=None,
        )

    with pytest.raises(TypeError, match='nested must be a list, not tuple'):
        _hit_resolve(
            CacheMethod.GET_OR_SET,
            args=arguments,
            kwargs=keywords,
            nested=nesting,  # ty:ignore[invalid-argument-type]
            result=None,
        )


def test_hits_and_misses_refuse_calls_that_are_no_list() -> None:
    calls = ()

    with pytest.raises(TypeError, match='calls must be a list, not tuple'):
        _hits_misses(calls)  # ty:ignore[invalid-argument-type]


def test_a_wrapper_refuses_an_uncallable_original_or_an_unknown_method() -> None:
    with pytest.raises(TypeError, match='original must be callable, not str'):
        _wrapper_build(
            'get',  # ty:ignore[invalid-argument-type]
            alias='default',
            method=CacheMethod.GET,
        )

    with pytest.raises(TypeError, match="method must be a CacheMethod: 'get'"):
        _wrapper_build(len, alias='default', method='get')  # ty:ignore[invalid-argument-type]


def test_a_cache_attribute_that_is_not_callable_is_left_unpatched() -> None:
    backend = SimpleNamespace(get='not callable')

    _cache_patch(backend, 'odd')

    assert backend.get == 'not callable'


def test_cache_panel_refuses_more_calls_than_it_holds(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    monkeypatch.setattr(cache_panel, 'CACHE_CALLS_MAX', 1)

    panel = CachePanel()
    request = request_factory.get('/')
    response = HttpResponse()
    context = KaleidoscopeContext()
    calls = [{'hit': False, 'method': 'GET'}, {'hit': False, 'method': 'GET'}]

    cache_panel._collecting.set(calls)

    with pytest.raises(RuntimeError, match='holds 2 calls, over the limit of 1'):
        panel.process_response(request, response, context)

    assert cache_panel._collecting.get() is None
    assert panel.get_data()['calls'] == []


class _ResultUnsized:
    def __bool__(self) -> bool:
        message = 'truthiness refused'
        raise RuntimeError(message)


def _get_many_unsized(keys: list[str]) -> _ResultUnsized:
    _ = keys

    return RESULT_UNSIZED


RESULT_UNSIZED = _ResultUnsized()


def test_a_get_many_result_without_a_length_never_breaks_the_host_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[dict] = []

    result = _call_tracked(
        _get_many_unsized,
        alias='default',
        args=(['alpha', 'beta'],),
        calls=calls,
        kwargs={},
        method=CacheMethod.GET_MANY,
    )

    assert result is RESULT_UNSIZED
    assert calls[0]['method'] == 'GET_MANY'
    assert calls[0]['hit'] is False
    assert 'could not tell whether a cache GET_MANY call hit' in caplog.text
