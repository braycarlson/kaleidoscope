from __future__ import annotations

import time

import sqlparse

from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from django.db import DatabaseError, connections, transaction
from django.http import HttpRequest, HttpResponseBase, JsonResponse

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panel import Panel, RequestHook, ResponseHook, ServerTimingMetric
from kaleidoscope.store import (
    QUERIES_PER_REQUEST_MAX,
    QUERY_SQL_LENGTH_MAX,
    CapturedRequest,
    QueryCapture,
    QueryStore,
)

if TYPE_CHECKING:
    from django.http import HttpResponse


EXPLAIN_REQUEST_ID_LENGTH_MAX = 64
EXPLAIN_ROWS_MAX = 1_000
EXPLAIN_TEXT_LENGTH_MAX = 100_000

EXPLAIN_VENDOR_OPTIONS = MappingProxyType({
    'postgresql': MappingProxyType({'analyze': True, 'buffers': True}),
})

_EXPLAIN_OPTIONS_NONE = MappingProxyType({})


class QueryAction(StrEnum):
    CLEAR = 'clear'
    EXPLAIN = 'explain'
    TRACK_AJAX_OFF = 'track-ajax-off'
    TRACK_AJAX_ON = 'track-ajax-on'
    TRACK_PAGE_OFF = 'track-page-off'
    TRACK_PAGE_ON = 'track-page-on'


def _explain_line(row: tuple) -> str:
    if len(row) == 1:
        return str(row[0])

    return ' '.join(str(value) for value in row)


def _explain_refusal(query: dict) -> str | None:
    if query['many']:
        return 'an executemany statement cannot be explained'

    if _statement_kind(query['raw_sql']) != 'SELECT':
        return 'only a SELECT can be explained'

    if len(query['sql']) > QUERY_SQL_LENGTH_MAX:
        return 'the statement was too long to capture whole'

    if query['params'] is not None:
        if query['sql'] == query['raw_sql']:
            return 'the statement was captured without its parameters'

    if query['alias'] not in connections:
        return f'the database {query["alias"]!r} is not configured'

    return None


def _explain_run(query: dict) -> dict:
    alias = query['alias']
    connection = connections[alias]
    options = EXPLAIN_VENDOR_OPTIONS.get(connection.vendor, _EXPLAIN_OPTIONS_NONE)
    command = connection.ops.explain_query_prefix(**options)
    statement = f'{command} {query["sql"]}'

    with transaction.atomic(using=alias):
        with connection.cursor() as cursor:
            cursor.execute(statement)
            rows = cursor.fetchmany(EXPLAIN_ROWS_MAX)

        transaction.set_rollback(True, using=alias)

    plan = '\n'.join(_explain_line(row) for row in rows)

    return {'command': command, 'plan': plan[:EXPLAIN_TEXT_LENGTH_MAX]}


def _query_time_ms(queries: list[dict]) -> float:
    if not isinstance(queries, list):
        message = f'queries must be a list, not {type(queries).__name__}'
        raise TypeError(message)

    time_ms = round(sum(query['time'] for query in queries) * 1000, 2)

    if time_ms < 0:
        message = f'the queries took a negative time: {time_ms}'
        raise RuntimeError(message)

    return time_ms


def _statement_kind(sql: str) -> str:
    try:
        statements = sqlparse.parse(sql)
    except Exception:
        statements = ()

    if not statements:
        return 'UNKNOWN'

    return statements[0].get_type()


class QueriesPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'queries'
    title = 'SQL Queries'

    def __init__(self) -> None:
        super().__init__()

        self.store = QueryStore()
        self.track_ajax = True
        self.track_page = True

    def _explain_respond(self, request: HttpRequest) -> HttpResponse:
        if not isinstance(request, HttpRequest):
            message = f'{self.title} needs an HttpRequest, not {type(request).__name__}'
            raise TypeError(message)

        request_id = request.GET.get('request', '')

        if not request_id:
            return JsonResponse({'error': 'invalid params'}, status=400)

        if len(request_id) > EXPLAIN_REQUEST_ID_LENGTH_MAX:
            return JsonResponse({'error': 'invalid params'}, status=400)

        try:
            query_index = int(request.GET.get('query', '-1'))
        except ValueError:
            return JsonResponse({'error': 'invalid params'}, status=400)

        captured = self.store.request_find(request_id)

        if captured is None:
            return JsonResponse({'error': 'request not found'}, status=404)

        if query_index < 0:
            return JsonResponse({'error': 'query not found'}, status=404)

        if query_index >= len(captured.queries):
            return JsonResponse({'error': 'query not found'}, status=404)

        query = captured.queries[query_index]
        refusal = _explain_refusal(query)

        if refusal is not None:
            return JsonResponse({'error': refusal}, status=400)

        try:
            explained = _explain_run(query)
        except (DatabaseError, ValueError) as exception:
            return JsonResponse({'error': str(exception)}, status=400)

        return JsonResponse(explained)

    def get_data(self) -> dict:
        data = self.store.data
        data['track_ajax'] = self.track_ajax
        data['track_page'] = self.track_page

        return data

    def get_server_timing(self, context: KaleidoscopeContext) -> list[ServerTimingMetric]:
        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        capture = context.state.get(self.panel_id)

        if capture is None:
            return []

        count = len(capture.queries)

        if count == 0:
            return []

        metric = ServerTimingMetric(
            key='sql_count',
            description=f'SQL {count} queries',
            duration=_query_time_ms(capture.queries),
        )

        return [metric]

    def get_summary(self) -> str:
        summary = self.store.summary

        if summary['total_queries']:
            return f'{summary["total_queries"]} queries, {summary["total_query_time"]} ms'

        return '0 queries'

    def handle_action(self, action: str, request: HttpRequest) -> HttpResponse | None:
        if not isinstance(action, str):
            message = f'action must be text: {action!r}'
            raise TypeError(message)

        if action == QueryAction.CLEAR:
            self.store.clear()

            return JsonResponse({'success': True})

        if action == QueryAction.EXPLAIN:
            return self._explain_respond(request)

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

        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        tracked = self.track_ajax if context.is_ajax else self.track_page

        if not tracked:
            return

        capture = QueryCapture()
        context.state[self.panel_id] = capture

        capture.attach()

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        if not isinstance(request, HttpRequest):
            message = f'{self.title} needs an HttpRequest, not {type(request).__name__}'
            raise TypeError(message)

        if not isinstance(response, HttpResponseBase):
            message = f'{self.title} needs an HttpResponse, not {type(response).__name__}'
            raise TypeError(message)

        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        capture = context.state.get(self.panel_id)

        if capture is None:
            return

        capture.detach()

        duration_ms = (time.perf_counter_ns() - context.started_ns) / 1_000_000
        queries = capture.queries

        if len(queries) > QUERIES_PER_REQUEST_MAX:
            message = f'the capture holds {len(queries)} queries, over {QUERIES_PER_REQUEST_MAX}'
            raise RuntimeError(message)

        captured = CapturedRequest(
            duration=round(duration_ms, 2),
            is_ajax=context.is_ajax,
            method=request.method or 'UNKNOWN',
            path=request.get_full_path(),
            queries=queries,
            query_count=len(queries),
            query_time=_query_time_ms(queries),
            request_id=context.request_id,
            status_code=response.status_code,
            timestamp=time.time(),
        )

        self.store.push(captured)
