from __future__ import annotations

import contextlib
import time

from typing import TYPE_CHECKING

from django.db import connection
from django.http import JsonResponse

from kaleidoscope.constants import QueryAction, StateKey
from kaleidoscope.panel import Panel, RequestHook, ResponseHook, ServerTimingMetric
from kaleidoscope.store import CapturedRequest, QueryCapture, QueryStore

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext


class QueriesPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'queries'
    title = 'SQL Queries'

    def __init__(self, store: QueryStore) -> None:
        super().__init__()

        self.store = store
        self.track_ajax = True
        self.track_page = True

    def get_data(self) -> dict:
        data = self.store.data

        data['track_ajax'] = self.track_ajax
        data['track_page'] = self.track_page

        return data

    def get_server_timing(self) -> list[ServerTimingMetric]:
        summary = self.store.summary

        if summary['total_queries']:
            return [
                ServerTimingMetric(
                    key='sql_count',
                    description=f'SQL {summary["total_queries"]} queries',
                    duration=summary['total_query_time'],
                ),
            ]

        return []

    def get_summary(self) -> str:
        summary = self.store.summary

        if summary['total_queries']:
            return f'{summary["total_queries"]} queries, {summary["total_query_time"]} ms'

        return '0 queries'

    def handle_action(self, action: str, request: HttpRequest) -> HttpResponse | None:
        _ = request

        if action == QueryAction.CLEAR:
            self.store.clear()
            return JsonResponse({'success': True})

        if action == QueryAction.TRACK_AJAX_ON:
            self.track_ajax = True
            return JsonResponse({'track_ajax': True})

        if action == QueryAction.TRACK_AJAX_OFF:
            self.track_ajax = False
            return JsonResponse({'track_ajax': False})

        if action == QueryAction.TRACK_PAGE_ON:
            self.track_page = True
            return JsonResponse({'track_page': True})

        if action == QueryAction.TRACK_PAGE_OFF:
            self.track_page = False
            return JsonResponse({'track_page': False})

        return None

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request

        if context.is_ajax and not self.track_ajax:
            return

        if not context.is_ajax and not self.track_page:
            return

        capture = QueryCapture()
        context.state[StateKey.QUERY_CAPTURE] = capture
        context.state[StateKey.QUERY_START] = time.perf_counter_ns()

        connection.execute_wrappers.append(capture)

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        capture = context.state.get(StateKey.QUERY_CAPTURE)

        if not capture:
            return

        with contextlib.suppress(ValueError):
            connection.execute_wrappers.remove(capture)

        start = context.state[StateKey.QUERY_START]

        duration = (time.perf_counter_ns() - start) / 1_000_000
        queries = capture.queries
        query_time = sum(query['time'] for query in queries) * 1000

        method = request.method or 'UNKNOWN'

        captured = CapturedRequest(
            duration=round(duration, 2),
            is_ajax=context.is_ajax,
            method=method,
            path=request.get_full_path(),
            queries=queries,
            query_count=len(queries),
            query_time=round(query_time, 2),
            status_code=response.status_code,
            timestamp=time.time(),
        )

        self.store.push(captured)
