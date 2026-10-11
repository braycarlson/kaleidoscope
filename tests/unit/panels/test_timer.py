from __future__ import annotations

import time

import pytest

from typing import TYPE_CHECKING

from django.http import HttpResponse

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.injector import HEADER_SERVER_TIMING
from kaleidoscope.panels.timer import TimerPanel

from tests.toolbar import HEADERS_AJAX, panel_data, panels_listed

if TYPE_CHECKING:
    from django.test import Client, RequestFactory


@pytest.mark.django_db
def test_timer_records_the_last_page_load(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?status=201&kind=json')

    data = panel_data(toolbar_client, 'timer')

    assert data['method'] == 'GET'
    assert data['path'].startswith('/work/?')
    assert data['status_code'] == 201
    assert data['content_type'] == 'application/json'
    assert data['asgi'] is False
    assert data['total_ms'] >= 0.0


@pytest.mark.django_db
def test_timer_keeps_the_page_when_ajax_arrives_but_times_the_ajax_response(
    toolbar_client: Client,
) -> None:
    toolbar_client.get('/plain/')
    response = toolbar_client.get('/work/', headers=HEADERS_AJAX)

    assert panel_data(toolbar_client, 'timer')['path'] == '/plain/'
    assert 'timer_total;dur=' in response[HEADER_SERVER_TIMING]


@pytest.mark.django_db
def test_timer_summary_names_the_method_and_time(toolbar_client: Client) -> None:
    toolbar_client.get('/plain/')

    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}

    assert summaries['timer'].startswith('GET ')
    assert summaries['timer'].endswith(' ms')


def test_timer_summary_is_empty_before_any_page() -> None:
    assert TimerPanel().get_summary() == ''


def test_timer_reports_no_server_timing_before_it_measured() -> None:
    assert TimerPanel().get_server_timing(KaleidoscopeContext()) == []


def test_timer_refuses_to_report_a_negative_duration() -> None:
    context = KaleidoscopeContext(state={'timer': -1.5})

    with pytest.raises(RuntimeError, match='Timer measured a negative duration'):
        TimerPanel().get_server_timing(context)


def test_timer_fails_loudly_on_a_request_that_started_in_the_future(
    request_factory: RequestFactory,
) -> None:
    panel = TimerPanel()
    context = KaleidoscopeContext(started_ns=time.perf_counter_ns() + 10**12)
    request = request_factory.get('/')
    response = HttpResponse()

    with pytest.raises(RuntimeError, match='Timer measured a negative duration'):
        panel.process_response(request, response, context)

    assert 'timer' not in context.state
    assert panel.get_data() == {}
