from __future__ import annotations

import functools

import pytest

from types import SimpleNamespace
from typing import TYPE_CHECKING

from django.http import HttpResponse
from django.template import Template
from django.test import override_settings
from django.views import View
from pyinstrument import Profiler

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panels import line_profiling, memory
from kaleidoscope.panels.line_profiling import (
    LineProfilingPanel,
    _function_result,
    _functions_resolved,
    _path_shortened,
    _results_build,
)
from kaleidoscope.panels.memory import (
    MEMORY_DIFF_ROWS_MAX,
    MemoryPanel,
    _category_of,
    _diff_rows,
    _is_integer_cached,
    _size_text,
    _summarized,
    _summary_footprint,
)
from kaleidoscope.panels.profiling import ProfilingPanel, _profile_html, _profile_text

from tests.testapp import cache as testapp_cache
from tests.testapp.work import SPIN_MS, spin_for_profile
from tests.toolbar import HEADERS_AJAX, panel_action, panel_data, panel_toggle, panels_listed

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.template import Context
    from django.test import Client, RequestFactory


RENDER_UNSPUN = Template._render


def _cache_spinning(operation: str) -> None:
    _ = operation

    spin_for_profile(SPIN_MS)


def _render_spinning(template: Template, context: Context) -> str:
    spin_for_profile(SPIN_MS)

    return RENDER_UNSPUN(template, context)


def _view_function(request: HttpRequest) -> HttpResponse:
    _ = request
    total = 0

    for index in range(50):
        total += index

    return HttpResponse(str(total))


class _ProfilerBytes:
    def output_html(self) -> bytes:
        return b'<html></html>'

    def output_text(self, **keywords: object) -> bytes:
        _ = keywords

        return b'text'


class _ProfilerBroken:
    def output_html(self) -> str:
        message = 'no html for you'
        raise RuntimeError(message)

    def output_text(self, **keywords: object) -> str:
        _ = keywords
        message = 'no text for you'

        raise RuntimeError(message)


class _ViewBare:
    pass


class _ViewClass(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        return _view_function(request)


def _resolve_to(monkeypatch: pytest.MonkeyPatch, func: object) -> None:
    match = SimpleNamespace(func=func)

    def resolve(path: str) -> SimpleNamespace:
        _ = path

        return match

    monkeypatch.setattr(line_profiling, 'resolve', resolve)


@pytest.mark.parametrize(
    ('type_name', 'expected'),
    [
        ('builtins.dict', 'builtin'),
        ('dict', 'builtin'),
        ('function (helper)', 'stdlib'),
        ('collections.OrderedDict', 'stdlib'),
        ('_io.TextIOWrapper', 'stdlib'),
        ('django.db.models.base.ModelState', 'django'),
        ('tests.testapp.models.Author', 'project'),
    ],
)
def test_memory_category_ofs_each_type_by_its_origin(type_name: str, expected: str) -> None:
    assert _category_of(type_name) == expected


@pytest.mark.parametrize(
    ('size', 'expected'),
    [
        (0, '0 B'),
        (1023, '1023 B'),
        (2048, '2.0 KB'),
        (-2048, '-2.0 KB'),
        (5 * 1024 * 1024, '5.00 MB'),
    ],
)
def test_memory_formats_sizes_in_binary_units(size: int, expected: str) -> None:
    assert _size_text(size) == expected


@pytest.mark.django_db
def test_memory_panel_reports_the_heap_difference_and_pauses_the_others(
    toolbar_client: Client,
) -> None:
    panel_toggle(toolbar_client, 'memory', enabled=True)
    toolbar_client.get('/work/?queries=2')

    data = panel_data(toolbar_client, 'memory')

    assert 0 < len(data['diff']) <= MEMORY_DIFF_ROWS_MAX
    assert data['total_objects'] > 0
    assert data['total_size_display'].endswith(('B', 'KB', 'MB'))
    assert panel_data(toolbar_client, 'queries')['requests'] == []


@pytest.mark.django_db
def test_profiling_panel_captures_a_profile_of_the_page(toolbar_client: Client) -> None:
    panel_toggle(toolbar_client, 'profiling', enabled=True)
    toolbar_client.get('/work/?queries=10&templates=3')

    data = panel_data(toolbar_client, 'profiling')

    assert data['has_data'] is True
    assert data['duration_ms'] >= 0.0
    assert '<html' in data['html'].lower()

    response = panel_action(toolbar_client, 'profiling', 'html')

    assert response.status_code == 200
    assert response['Content-Type'].startswith('text/html')


def test_profiling_panel_html_action_explains_an_empty_profile(toolbar_client: Client) -> None:
    response = panel_action(toolbar_client, 'profiling', 'html')

    assert response.status_code == 200
    assert b'No profile captured yet' in response.content


def test_profiling_panel_survives_a_profiler_that_never_started(
    request_factory: RequestFactory,
) -> None:
    panel = ProfilingPanel()
    context = KaleidoscopeContext()
    context.state['profiling'] = Profiler()
    request = request_factory.get('/')
    response = HttpResponse()

    panel.process_response(request, response, context)

    data = panel.get_data()

    assert data['has_data'] is False
    assert 'Profiler stop failed' in data['text']


def test_line_profiler_resolves_a_function_view(request_factory: RequestFactory) -> None:
    request = request_factory.get('/work/')
    functions = _functions_resolved(request)

    assert [function.__name__ for function in functions] == ['work_view']


def test_line_profiler_resolves_nothing_for_an_unknown_path(
    request_factory: RequestFactory,
) -> None:
    request = request_factory.get('/no/such/path/')

    assert _functions_resolved(request) == []


def test_line_profiler_resolves_the_handler_and_dispatch_of_a_class_view(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    match = SimpleNamespace(func=_ViewClass.as_view())

    def resolve(path: str) -> SimpleNamespace:
        _ = path

        return match

    monkeypatch.setattr('kaleidoscope.panels.line_profiling.resolve', resolve)

    request = request_factory.get('/class/')
    functions = _functions_resolved(request)

    assert [function.__name__ for function in functions] == ['get', 'dispatch']


def test_line_profiler_unwraps_a_decorated_view(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    @functools.wraps(_view_function)
    def decorated(request: HttpRequest) -> HttpResponse:
        return _view_function(request)

    match = SimpleNamespace(func=decorated)

    def resolve(path: str) -> SimpleNamespace:
        _ = path

        return match

    monkeypatch.setattr('kaleidoscope.panels.line_profiling.resolve', resolve)

    request = request_factory.get('/decorated/')
    functions = _functions_resolved(request)

    assert functions == [_view_function]


@pytest.mark.django_db
def test_line_profiler_times_the_lines_of_the_view(toolbar_client: Client) -> None:
    panel_toggle(toolbar_client, 'line_profiling', enabled=True)
    toolbar_client.get('/work/?queries=3')

    data = panel_data(toolbar_client, 'line_profiling')

    assert data['has_data'] is True
    assert data['function_count'] >= 1

    function = data['functions'][0]

    assert function['func_name'] == 'work_view'
    assert any('queries_run(plan)' in line['source'] for line in function['lines'])


def test_line_profiler_builds_no_result_from_empty_stats() -> None:
    stats = SimpleNamespace(timings={}, unit=1e-6)

    assert _results_build(stats) == []


@pytest.mark.parametrize(
    ('path', 'expected'),
    [
        ('short.py', 'short.py'),
        ('/a/b/c.py', '/a/b/c.py'),
        ('/home/user/project/app/views.py', '.../project/app/v...'),
        ('C:\\Users\\user\\project\\app\\views.py', '.../project/app/v...'),
    ],
)
def test_path_shortened_keeps_the_tail_within_its_length(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    expected: str,
) -> None:
    monkeypatch.setattr(line_profiling, 'PATH_LENGTH_MAX', 20)

    assert _path_shortened(path) == expected


@pytest.mark.parametrize(
    'path',
    ['/a/b/c.py', '/home/user/project/app/views.py', 'x' * 500, 'C:\\a\\b\\c\\d\\e\\f.py'],
)
def test_path_shortened_never_makes_a_path_longer(path: str) -> None:
    assert len(_path_shortened(path)) <= len(path)


def test_memory_panel_skips_ajax_requests(request_factory: RequestFactory) -> None:
    panel = MemoryPanel()
    context = KaleidoscopeContext(is_ajax=True)
    request = request_factory.get('/')
    response = HttpResponse('{}', content_type='application/json')

    panel.process_request(request, context)
    panel.process_response(request, response, context)

    assert panel.get_data() == {}
    assert panel.get_summary() == ''


def test_profiling_output_failures_are_explained_in_the_output() -> None:
    profiler = _ProfilerBroken()

    assert 'HTML output failed: no html for you' in _profile_html(profiler, 1.5)
    assert 'text output failed: no text for you' in _profile_text(profiler, 1.5)


def test_profiling_panel_handles_only_its_html_action(request_factory: RequestFactory) -> None:
    request = request_factory.get('/')

    assert ProfilingPanel().handle_action('other', request) is None


def test_profiling_panel_keeps_its_data_when_the_profiler_kept_no_session(
    request_factory: RequestFactory,
) -> None:
    panel = ProfilingPanel()
    profiler = SimpleNamespace(last_session=None, stop=lambda: None)
    context = KaleidoscopeContext(state={'profiling': profiler})
    request = request_factory.get('/')

    panel.process_response(request, HttpResponse(), context)

    assert panel.get_data() == {}


def test_line_profiler_resolves_nothing_for_a_class_view_without_handlers(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    view = SimpleNamespace(view_class=_ViewBare)

    _resolve_to(monkeypatch, view)

    assert _functions_resolved(request_factory.post('/bare/')) == []


def test_line_profiler_rejects_a_cyclic_decorator_chain(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    def view_cyclic(request: HttpRequest) -> HttpResponse:
        return _view_function(request)

    view_cyclic.__wrapped__ = view_cyclic

    _resolve_to(monkeypatch, view_cyclic)

    with pytest.raises(ValueError, match='wrapper loop'):
        _functions_resolved(request_factory.get('/cyclic/'))


def test_line_profiler_profiles_nothing_for_a_path_without_a_view(
    request_factory: RequestFactory,
) -> None:
    panel = LineProfilingPanel()
    context = KaleidoscopeContext()
    request = request_factory.get('/no/such/path/')

    panel.process_request(request, context)
    panel.process_response(request, HttpResponse(), context)

    assert 'line_profiling' not in context.state
    assert panel.get_data() == {}


def test_line_profiler_skips_functions_that_recorded_no_lines() -> None:
    stats = SimpleNamespace(timings={('views.py', 1, 'view'): []}, unit=1e-6)

    assert _results_build(stats) == []


def test_line_profiler_times_a_call_chain_by_its_outermost_function(
    request_factory: RequestFactory,
) -> None:
    timings = {
        ('views.py', 1, 'dispatch'): [(2, 1, 3_000)],
        ('views.py', 5, 'get'): [(6, 1, 2_000)],
    }

    stats = SimpleNamespace(timings=timings, unit=1e-6)
    profiler = SimpleNamespace(disable_by_count=lambda: None, get_stats=lambda: stats)
    context = KaleidoscopeContext(state={'line_profiling': profiler})
    panel = LineProfilingPanel()
    request = request_factory.get('/')

    panel.process_response(request, HttpResponse(), context)

    assert panel.get_data()['duration_ms'] == 3.0


def test_path_shortened_keeps_a_short_tail_whole() -> None:
    path = '/' + 'long-directory-name/' * 6 + 'app/views/index.py'

    assert _path_shortened(path) == '.../app/views/index.py'


@pytest.mark.django_db
def test_profiling_panel_summarizes_its_profile_and_skips_ajax(toolbar_client: Client) -> None:
    panel_toggle(toolbar_client, 'profiling', enabled=True)
    toolbar_client.get('/work/?queries=2')

    data = panel_data(toolbar_client, 'profiling')

    toolbar_client.get('/work/?queries=2', headers=HEADERS_AJAX)

    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}

    assert panel_data(toolbar_client, 'profiling') == data
    assert summaries['profiling'] == f'{data["duration_ms"]:.0f} ms'


@pytest.mark.django_db
def test_line_profiler_summarizes_its_functions_and_skips_ajax(toolbar_client: Client) -> None:
    panel_toggle(toolbar_client, 'line_profiling', enabled=True)
    toolbar_client.get('/work/?queries=2')

    data = panel_data(toolbar_client, 'line_profiling')

    toolbar_client.get('/work/?queries=2', headers=HEADERS_AJAX)

    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}
    summary = f'{data["function_count"]} functions, {data["duration_ms"]:.0f} ms'

    assert panel_data(toolbar_client, 'line_profiling') == data
    assert summaries['line_profiling'] == summary


@pytest.mark.django_db
@override_settings(
    MIDDLEWARE=[
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'kaleidoscope.middleware.KaleidoscopeMiddleware',
    ],
    X_FRAME_OPTIONS='DENY',
)
def test_profiling_panel_html_can_be_framed_by_the_toolbar_page(toolbar_client: Client) -> None:
    response = panel_action(toolbar_client, 'profiling', 'html')

    assert response.status_code == 200
    assert response['X-Frame-Options'] == 'SAMEORIGIN'


@pytest.mark.parametrize(
    ('value', 'expected'),
    [(-5, True), (256, True), (-6, False), (257, False), ('5', False)],
)
def test_memory_knows_which_integers_the_interpreter_shares(value: object, expected: bool) -> None:
    assert _is_integer_cached(value) is expected


def test_memory_footprint_counts_the_rows_of_a_snapshot_but_not_shared_integers() -> None:
    snapshot = [['builtins.str', 3, 300_000]]
    footprint = {row[0]: row[1] for row in _summary_footprint(snapshot)}

    assert footprint == {'list': 2, 'str': 1, 'int': 1}


def test_memory_diff_subtracts_the_footprint_and_drops_unchanged_rows() -> None:
    before = [['list', 10, 800], ['str', 5, 250], ['dict', 1, 100]]
    after = [['list', 13, 1040], ['str', 6, 300], ['dict', 1, 100]]
    footprint = [['list', 3, 240]]

    assert _diff_rows(before, after, footprint) == [['str', 1, 50]]


@pytest.mark.django_db
def test_memory_panel_leaves_its_own_snapshot_out_of_the_difference(toolbar_client: Client) -> None:
    panel_toggle(toolbar_client, 'memory', enabled=True)
    toolbar_client.get('/plain/')

    counts = {row['type']: row['count'] for row in panel_data(toolbar_client, 'memory')['diff']}

    assert counts.get('list', 0) < 100
    assert counts.get('str', 0) < 100


@pytest.mark.django_db
def test_the_profile_of_an_isolated_page_holds_no_toolbar_instrumentation(
    toolbar_client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Template, '_render', _render_spinning)
    monkeypatch.setattr(testapp_cache, 'fault_hook', _cache_spinning)
    toolbar_client.get('/work/?templates=1&cache=get:alpha')
    panel_toggle(toolbar_client, 'profiling', enabled=True)
    toolbar_client.get('/work/?templates=1&cache=get:alpha')

    text = panel_data(toolbar_client, 'profiling')['text']

    assert '_render_spinning' in text
    assert '_cache_spinning' in text
    assert 'render_tracked' not in text
    assert 'panels/cache.py' not in text


def _objects_none() -> list:
    return []


def _profiler_stopped() -> None:
    return


def _summary_tuple(objects: list) -> tuple:
    _ = objects

    return ()


def _summary_small() -> list:
    return [['dict', 1, 100]]


def _footprint_many_objects(summary: list) -> list:
    _ = summary

    return [['list', 5, 50]]


def _footprint_many_bytes(summary: list) -> list:
    _ = summary

    return [['list', 0, 500]]


def test_memory_category_refuses_a_type_name_that_is_not_text() -> None:
    with pytest.raises(TypeError, match='type_name must be text: 7'):
        _category_of(7)  # ty:ignore[invalid-argument-type]


@pytest.mark.parametrize('position', ['before', 'after', 'footprint'])
def test_memory_diff_refuses_a_summary_that_is_no_list(position: str) -> None:
    summaries = {'after': [], 'before': [], 'footprint': []}
    summaries[position] = ()

    with pytest.raises(TypeError, match=f'{position} must be a summary list, not tuple'):
        _diff_rows(**summaries)


@pytest.mark.parametrize(
    ('size', 'pattern'),
    [(True, 'size must be an integer, not a bool'), (1.5, 'size must be an integer: 1.5')],
)
def test_memory_size_text_refuses_a_size_that_is_no_integer(size: object, pattern: str) -> None:
    with pytest.raises(TypeError, match=pattern):
        _size_text(size)  # ty:ignore[invalid-argument-type]


def test_memory_refuses_a_heap_summary_that_is_no_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory.muppy, 'get_objects', _objects_none)
    monkeypatch.setattr(memory.pympler_summary, 'summarize', _summary_tuple)

    with pytest.raises(TypeError, match='summarized the heap as a tuple, not a list'):
        _summarized()


def test_memory_footprint_refuses_a_summary_that_is_no_list_of_rows() -> None:
    summary = ()
    rows = [['builtins.str', 1]]

    with pytest.raises(TypeError, match='summary must be a list, not tuple'):
        _summary_footprint(summary)  # ty:ignore[invalid-argument-type]

    with pytest.raises(ValueError, match='holds a type, a count, and a size'):
        _summary_footprint(rows)


@pytest.mark.parametrize(
    ('footprint', 'pattern'),
    [
        (_footprint_many_objects, 'the heap holds -4 objects'),
        (_footprint_many_bytes, 'the heap holds -400 bytes'),
    ],
)
def test_memory_panel_fails_loudly_when_its_snapshot_outweighs_the_heap(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
    footprint: object,
    pattern: str,
) -> None:
    monkeypatch.setattr(memory, '_summarized', _summary_small)
    monkeypatch.setattr(memory, '_summary_footprint', footprint)

    panel = MemoryPanel()
    context = KaleidoscopeContext(state={'memory': [['dict', 1, 100]]})
    request = request_factory.get('/')
    response = HttpResponse()

    with pytest.raises(RuntimeError, match=pattern):
        panel.process_response(request, response, context)

    assert panel.get_data() == {}


def test_profiling_output_refuses_a_negative_duration() -> None:
    profiler = _ProfilerBroken()

    with pytest.raises(ValueError, match='duration_ms must not be negative: -1'):
        _profile_html(profiler, -1.0)  # ty:ignore[invalid-argument-type]

    with pytest.raises(ValueError, match='duration_ms must not be negative: -1'):
        _profile_text(profiler, -1.0)  # ty:ignore[invalid-argument-type]


def test_profiling_output_refuses_a_profiler_that_renders_bytes() -> None:
    profiler = _ProfilerBytes()

    with pytest.raises(TypeError, match='rendered its HTML as a bytes, not text'):
        _profile_html(profiler, 1.0)  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='rendered its text as a bytes, not text'):
        _profile_text(profiler, 1.0)  # ty:ignore[invalid-argument-type]


def test_profiling_panel_fails_loudly_on_a_session_that_ran_backwards(
    request_factory: RequestFactory,
) -> None:
    panel = ProfilingPanel()
    session = SimpleNamespace(duration=-0.5)
    profiler = SimpleNamespace(last_session=session, stop=_profiler_stopped)
    context = KaleidoscopeContext(state={'profiling': profiler})
    request = request_factory.get('/')
    response = HttpResponse()

    with pytest.raises(RuntimeError, match='measured a negative duration: -500'):
        panel.process_response(request, response, context)

    assert panel.get_data() == {}


def test_line_profiler_result_refuses_timings_that_are_no_list_or_a_unit_below_zero() -> None:
    timings_tuple = ()
    timings: list = []

    with pytest.raises(TypeError, match='timings must be a list, not tuple'):
        _function_result(
            'views.py',
            1,
            'view',
            timings_tuple,  # ty:ignore[invalid-argument-type]
            1e-6,
        )

    with pytest.raises(ValueError, match='unit must be positive: 0'):
        _function_result('views.py', 1, 'view', timings, 0)


def test_line_profiler_refuses_something_that_is_not_a_request() -> None:
    with pytest.raises(TypeError, match='resolves an HttpRequest, not NoneType'):
        _functions_resolved(None)  # ty:ignore[invalid-argument-type]


def test_path_shortened_refuses_a_path_that_is_not_text() -> None:
    with pytest.raises(TypeError, match='path must be text: 7'):
        _path_shortened(7)  # ty:ignore[invalid-argument-type]


@pytest.mark.parametrize(
    ('stats', 'error', 'pattern'),
    [
        (SimpleNamespace(timings=[], unit=1e-6), TypeError, 'its timings as a list'),
        (SimpleNamespace(timings={}, unit=0), ValueError, 'a unit that is not positive: 0'),
    ],
)
def test_line_profiler_results_refuse_malformed_stats(
    stats: object,
    error: type[Exception],
    pattern: str,
) -> None:
    with pytest.raises(error, match=pattern):
        _results_build(stats)
