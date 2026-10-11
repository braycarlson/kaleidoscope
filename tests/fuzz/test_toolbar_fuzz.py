from __future__ import annotations

import json

import pytest

from types import SimpleNamespace
from urllib.parse import quote, urlencode

from hypothesis import example, given
from hypothesis import strategies as st

from django.http import HttpResponse
from django.test import Client, override_settings

from kaleidoscope.injector import HEADER_SERVER_TIMING
from kaleidoscope.panel import ServerTimingMetric
from kaleidoscope.registry import DEFAULT_PANELS
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX

from tests.fuzz.settings import fuzz_settings
from tests.fuzz.strategies import FLOATS_ANY, TEXTS_HOSTILE, TOOLBAR_PATHS, json_strict_load
from tests.simulation.oracle import server_timing_entries
from tests.testapp import panels as answering
from tests.testapp.views import PAGE_DOCUMENT
from tests.toolbar import shell_text


pytestmark = [pytest.mark.fuzz, pytest.mark.django_db]

HEADER_NAMES = (
    'Accept',
    'Content-Type',
    'Cookie',
    'Sec-Fetch-Dest',
    'X-Custom',
    'X-Kaleidoscope-Hidden',
    'X-Requested-With',
)

METHODS = ('DELETE', 'GET', 'HEAD', 'OPTIONS', 'PATCH', 'POST', 'PUT')
PANELS_WITH_ANSWERING = (*DEFAULT_PANELS, 'tests.testapp.panels.AnsweringPanel')

ANSWERS = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        FLOATS_ANY,
        TEXTS_HOSTILE,
        st.binary(max_size=8),
        st.builds(object),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(TEXTS_HOSTILE, children, max_size=3),
    ),
    max_leaves=8,
)

METRICS_SHAPED = st.builds(SimpleNamespace, key=ANSWERS, description=ANSWERS, duration=ANSWERS)

METRICS_VALID = st.builds(
    ServerTimingMetric,
    key=st.text(min_size=1, max_size=20),
    description=TEXTS_HOSTILE,
    duration=FLOATS_ANY,
)

METRICS = st.one_of(METRICS_SHAPED, METRICS_VALID)
TIMINGS = st.one_of(ANSWERS, st.lists(st.one_of(METRICS, ANSWERS), max_size=3))
ACTION_ANSWERS = st.one_of(ANSWERS, st.builds(HttpResponse, TEXTS_HOSTILE))

STEP_VALUES = st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(), TEXTS_HOSTILE),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.sampled_from(['kind', 'name', 'index', 'x']), children, max_size=3),
    ),
    max_leaves=10,
)


def _ajax_expected(headers: dict[str, str]) -> bool:
    if headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True

    destination = headers.get('Sec-Fetch-Dest')

    if destination:
        return destination != 'document'

    accept = headers.get('Accept', '')

    return bool(accept and 'text/html' not in accept)


def _toolbar_answer_valid(response: HttpResponse) -> None:
    assert response.status_code in {200, 400, 404}

    if response['Content-Type'] == 'application/json':
        json_strict_load(response.content)


@fuzz_settings
@given(path=TOOLBAR_PATHS)
@example(path='static/\x00.js')
@example(path='panels/templates/action/value/')
def test_any_toolbar_path_is_answered_without_failing(path: str) -> None:
    client = Client(raise_request_exception=True)
    response = client.get(KALEIDOSCOPE_URL_PREFIX + quote(path, safe='/'))

    _toolbar_answer_valid(response)


@fuzz_settings
@given(
    path=st.one_of(TEXTS_HOSTILE, STEP_VALUES.map(json.dumps)),
    template=st.one_of(TEXTS_HOSTILE, st.integers().map(str)),
)
@example(path='[' * 3000 + ']' * 3000, template='0')
@example(path='[{"kind": "attr", "name": "__class__"}]', template='0')
def test_template_value_lookups_are_answered_without_failing(path: str, template: str) -> None:
    client = Client(raise_request_exception=True)

    client.get('/work/?templates=2&token=fuzzed')

    query = urlencode({'path': path, 'template': template})
    response = client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/templates/action/value/?{query}')

    _toolbar_answer_valid(response)


@fuzz_settings
@given(
    headers=st.dictionaries(st.sampled_from(HEADER_NAMES), TEXTS_HOSTILE, max_size=5),
    query=TEXTS_HOSTILE,
    method=st.sampled_from(METHODS),
)
@example(headers={'Accept': '*/*'}, query='', method='GET')
@example(headers={'Cookie': '\x00=\x00; ;;=='}, query='a=%00', method='POST')
def test_any_request_reaches_the_host_page_with_at_most_the_shell_added(
    headers: dict[str, str],
    query: str,
    method: str,
) -> None:
    client = Client(raise_request_exception=True)
    response = client.generic(method, f'/plain/?{quote(query)}', headers=headers)
    content = response.content.decode()
    hidden = headers.get('X-Kaleidoscope-Hidden') == '1'
    shell_expected = method != 'HEAD' and not hidden and not _ajax_expected(headers)

    assert response.status_code == 200

    if method == 'HEAD':
        assert content == ''
    elif shell_expected:
        assert content == PAGE_DOCUMENT.replace('</body>', shell_text() + '</body>')
    else:
        assert content == PAGE_DOCUMENT


@fuzz_settings
@given(
    body=st.binary(max_size=400),
    content_type=st.one_of(
        st.sampled_from([
            'multipart/form-data',
            'multipart/form-data; boundary=x',
            'application/x-www-form-urlencoded',
            'application/json',
            'text/plain',
        ]),
        TEXTS_HOSTILE,
    ),
)
@example(
    body=b'--x\r\nContent-Disposition: form-data; name="a"\r\n\r\n1\r\n--x--',
    content_type='multipart/form-data; boundary=x',
)
def test_any_body_reaches_a_view_that_reads_it(body: bytes, content_type: str) -> None:
    client = Client(raise_request_exception=True)
    response = client.post('/body/', body, content_type=content_type)

    assert response.status_code == 200
    assert int(response.content) == len(body)

    request_data = json_strict_load(
        client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/request/data/').content,
    )

    assert request_data['method'] == 'POST'


@fuzz_settings
@given(data=ANSWERS, summary=ANSWERS, timing=TIMINGS, action=ACTION_ANSWERS)
@example(data=[], summary=7, timing=None, action={'ok': True})
@example(
    data={'value': float('nan')},
    summary=None,
    timing=[SimpleNamespace(key='bad', description=None, duration='slow')],
    action='text',
)
def test_a_panel_answering_anything_never_breaks_the_page_or_the_toolbar(
    data: object,
    summary: object,
    timing: object,
    action: object,
) -> None:
    answering.answers.update(action=action, data=data, summary=summary, timing=timing)

    with override_settings(KALEIDOSCOPE_PANELS=PANELS_WITH_ANSWERING):
        client = Client(raise_request_exception=True)
        page = client.get('/plain/')
        listed = client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/')
        data_response = client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/answering/data/')
        action_response = client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/answering/action/any/')

    answering.answers.clear()
    panels = json_strict_load(listed.content)['panels']
    timing_header = page.get(HEADER_SERVER_TIMING, '')

    assert page.status_code == 200
    assert page.content.decode() == PAGE_DOCUMENT.replace('</body>', shell_text() + '</body>')
    assert server_timing_entries(timing_header) or timing_header == ''
    assert listed.status_code == 200
    assert [panel['id'] for panel in panels][-1] == 'answering'
    assert all(isinstance(panel['summary'], str) for panel in panels)
    assert data_response.status_code in {200, 500}
    assert isinstance(json_strict_load(data_response.content), dict)
    assert action_response.status_code in {200, 404, 500}
