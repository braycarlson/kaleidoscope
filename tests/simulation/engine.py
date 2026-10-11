from __future__ import annotations

import asyncio
import collections
import json
import random

import django.dispatch

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING
from unittest import mock
from urllib.parse import urlencode

from asgiref.sync import async_to_sync
from django.contrib.auth.models import PermissionsMixin
from django.core.cache import cache
from django.db import connections
from django.template import Template
from django.test import AsyncClient, Client
from django.test.client import BOUNDARY, encode_multipart

from kaleidoscope import injector, store
from kaleidoscope.injector import HEADER_REQUEST_ID, HEADER_SERVER_TIMING
from kaleidoscope.middleware import STATUS_CLIENT_CLOSED_REQUEST
from kaleidoscope.panels import cache as cache_panel
from kaleidoscope.panels import request as request_panel
from kaleidoscope.panels import signals as signals_panel
from kaleidoscope.panels import templates as templates_panel
from kaleidoscope.panels.settings import MASKED_VALUE
from kaleidoscope.patch import is_patched
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX

from tests.fuzz.strategies import json_strict_load
from tests.simulation.fault import FaultLedger, faults_installed
from tests.simulation.model import CapturedExpectation, PageExpectation, ToolbarModel
from tests.simulation.oracle import (
    body_expected,
    body_injected,
    cache_call_expected,
    cache_calls_expected,
    charset_of,
    check,
    injection_expected,
    server_timing_entries,
    static_used_expected,
)
from tests.simulation.swarm import swarmed
from tests.testapp import work
from tests.testapp.models import Author
from tests.testapp.views import PAGE_DOCUMENT
from tests.testapp.visibility import HEADER_HIDDEN
from tests.testapp.work import (
    CACHE_OPERATION_NAMES,
    KINDS,
    SERVER_TIMING_APPLICATION,
    CacheOperation,
    WorkPlan,
)
from tests.toolbar import (
    PANEL_IDS_DEFAULT,
    PANEL_IDS_ISOLATED,
    async_get,
    async_post,
    shell_text,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from django.http import HttpResponse

    from tests.simulation.fault import Faults
    from tests.simulation.run import Run


    Action = Callable[[Run], None]


ASYNC_ROUTE_CHANCE = 0.3
BATCH_CACHE_OPERATION_NAMES = ('add', 'del', 'get', 'getd', 'gos', 'has', 'set')
BATCH_CANCEL_CHANCE = 0.2
BATCH_CANCEL_TURNS_MAX = 6
BATCH_SIZES = (2, 3, 4)
CACHE_CALLS_SIMULATED = 40
CACHE_KEYS = ('alpha', 'beta', 'gamma', 'delta')
FORM_FIELDS = MappingProxyType({'field': 'value', 'other': 'second'})
LINGER_TURNS = (0, 0, 1, 2, 3, 5, 8)

CANARIES = (
    'canary-nested-password',
    'canary-nested-signature',
    'canary-nested-token',
    'canary-passwd-value',
    'canary-token-value',
)

HEADERS_AJAX = (
    {'X-Requested-With': 'XMLHttpRequest'},
    {'Accept': 'application/json'},
    {'Sec-Fetch-Dest': 'empty'},
)

HEADERS_PAGE = (
    {},
    {'Accept': 'text/html,application/xhtml+xml;q=0.9'},
    {'Sec-Fetch-Dest': 'document'},
)

HTML_TYPES = frozenset({'application/xhtml+xml', 'text/html'})
INJECTABLE_CONTENT_SIMULATED = 8_192

PATHS_GARBAGE = (
    'panels/missing/data/',
    'panels/queries/',
    'panels/queries/unknown/',
    'panels/queries/action/unknown/',
    'static/missing.js',
    'static/../router.py',
    'static/%00.js',
    'elsewhere/',
    '',
)

QUERY_ACTIONS = ('clear', 'track-ajax-off', 'track-ajax-on', 'track-page-off', 'track-page-on')
REQUESTS_STORED_SIMULATED = 6

SOMETIMES_TARGETS = (
    'ajax captured',
    'cache hit recorded',
    'cache miss recorded',
    'duplicates in one request',
    'form body read by the view',
    'hidden request untouched',
    'ignored request untouched',
    'isolation paused capture',
    'page injected',
    'page not injected',
    'queries action clear',
    'store at capacity',
    'template value 200',
    'template value 400',
    'template value 404',
    'toolbar garbage refused',
    'toolbar static served',
    'tracking skipped a request',
    'view failed',
)

SOMETIMES_TARGETS_ASGI = (
    'async page profiled',
    'batch request cancelled',
    'batch request recorded',
    'late query while another request captured',
)

STATIC_FILES = (
    ('kaleidoscope.js', 200),
    ('kaleidoscope.css', 200),
    ('missing.css', 404),
    ('../kaleidoscope.js', 404),
)

STATUSES_WEIGHTED = (200, 200, 200, 200, 201, 302, 404, 500)
VIEW_ASYNC = 'tests.testapp.views.work_async_view'
VIEW_SYNC = 'tests.testapp.views.work_view'

TEMPLATE_VALUE_PATHS = (
    json.dumps([{'kind': 'key', 'name': 'token'}]),
    json.dumps([{'kind': 'key', 'name': 'index'}]),
    json.dumps([{'kind': 'key', 'name': 'missing'}]),
    json.dumps([{'kind': 'key', 'name': 'token'}, {'kind': 'attr', 'name': '__class__'}]),
    '[' * 40 + ']' * 40,
    'not json',
    '{}',
)

TEMPLATE_VALUE_INDEXES = ('0', '1', '2', '-1', '99', 'x')

TOGGLE_PANEL_IDS = (
    'cache',
    'line_profiling',
    'profiling',
    'queries',
    'request',
    'signals',
    'staticfiles',
    'templates',
    'timer',
)


@dataclass
class _HostOutcome:
    active: dict[str, bool]
    body_length: int
    content: bytes
    is_ajax: bool
    method: str
    path: str
    plan: WorkPlan
    response: HttpResponse
    view: str
    view_faulted: bool
    visible: bool


def _batch_query_count_max(plan: WorkPlan) -> int:
    if plan.linger:
        return plan.queries + 1

    return plan.queries


def _content_of(response: HttpResponse) -> bytes:
    if getattr(response, 'streaming', False):
        return b''.join(response.streaming_content)

    return response.content


class ToolbarSimulation:
    def __init__(
        self,
        *,
        asgi: bool = False,
        faults: Faults | None = None,
        kinds: tuple[str, ...] = KINDS,
        toggles: tuple[str, ...] = TOGGLE_PANEL_IDS,
    ) -> None:
        self.asgi = asgi
        self.faults = faults
        self.kinds = kinds
        self.ledger = FaultLedger()
        self.toggles = toggles

        self.model = ToolbarModel(
            cache_calls_max=CACHE_CALLS_SIMULATED,
            requests_stored_max=REQUESTS_STORED_SIMULATED,
        )

        self._client: AsyncClient | Client | None = None
        self._templates_token: str | None = None
        self._token_index = 0

    def _batch_check(
        self,
        run: Run,
        plans: tuple[WorkPlan, ...],
        results: list[object],
        *,
        active: dict[str, bool],
        faulted: bool,
    ) -> None:
        path_data = f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/data/'
        response = async_get(self._client_ready(), path_data)
        records = json_strict_load(response.content)['requests']
        tracked = active['queries'] and self.model.tracking(is_ajax=True)

        for plan, result in zip(plans, results, strict=True):
            path = f'/work-async/?{plan.query_string()}'
            matching = [record for record in records if record['path'] == path]
            cancelled = isinstance(result, asyncio.CancelledError)

            check(len(matching) <= 1, f'a batch request was recorded twice: {path}')

            for record in matching:
                check(
                    record['query_count'] == len(record['queries']),
                    f'a batch request miscounts its queries: {record!r}',
                )

            if not tracked:
                check(not matching, f'an untracked batch request was recorded: {path}')

                continue

            if cancelled:
                self._batch_cancelled_check(run, plan, matching)

                continue

            if faulted:
                continue

            self._batch_completed_check(run, plan, result, matching)

    def _batch_cancelled_check(self, run: Run, plan: WorkPlan, matching: list[dict]) -> None:
        run.sometimes('batch request cancelled')

        statuses = {STATUS_CLIENT_CLOSED_REQUEST, 500 if plan.fail else plan.status}
        count_max = _batch_query_count_max(plan)

        for record in matching:
            check(record['status_code'] in statuses, f'a cancelled request shows {record!r}')
            check(record['query_count'] <= count_max, f'a cancelled request overcounts: {record}')

    def _batch_completed_check(
        self,
        run: Run,
        plan: WorkPlan,
        result: object,
        matching: list[dict],
    ) -> None:
        status_expected = 500 if plan.fail else plan.status

        status = getattr(result, 'status_code', None)

        check(len(matching) == 1, f'a batch request was not recorded: {plan.token}')
        check(status == status_expected, f'{plan.token} answered {status}, not {status_expected}')

        record = matching[0]
        count = record['query_count']
        count_max = _batch_query_count_max(plan)

        check(
            plan.queries <= count <= count_max,
            f'{plan.token} recorded {count} queries, expected {plan.queries}..{count_max}',
        )

        check(record['status_code'] == status_expected, f'{plan.token} recorded {record!r}')

        run.sometimes('batch request recorded')

    def _batch_model_update(self, active: dict[str, bool]) -> None:
        if active['queries']:
            if self.model.tracking(is_ajax=True):
                self.model.store_known = False

        if active['cache']:
            self.model.cache_calls_push(None, is_ajax=True)

        self._cache_present_resync()

    def _batch_plan_build(self, run: Run) -> WorkPlan:
        rng = run.rng
        self._token_index += 1
        operations = []

        for _ in range(rng.randint(0, 2)):
            name = rng.choice(BATCH_CACHE_OPERATION_NAMES)
            key = (rng.choice(CACHE_KEYS),)
            operation = CacheOperation(name=name, keys=key)

            operations.append(operation)

        return WorkPlan(
            cache_operations=tuple(operations),
            distinct=rng.randint(1, 4),
            fail=rng.random() < 0.1,
            kind='json',
            linger=rng.choice(LINGER_TURNS),
            queries=rng.randint(0, 6),
            status=rng.choice(STATUSES_WEIGHTED),
            token=f'batch-{run.seed % 10_000}-{self._token_index}',
        )

    async def _batch_run(
        self,
        plans: tuple[WorkPlan, ...],
        headers: dict[str, str],
        *,
        cancel_index: int | None,
        cancel_turns: int,
    ) -> tuple[list[object], list[object]]:
        client = self._client_ready()
        paths = [f'/work-async/?{plan.query_string()}' for plan in plans]
        tasks = [asyncio.ensure_future(client.get(path, headers=headers)) for path in paths]

        if cancel_index is not None:
            for _ in range(cancel_turns):
                await asyncio.sleep(0)

            tasks[cancel_index].cancel()

        results = await asyncio.gather(*tasks, return_exceptions=True)
        lingering = list(work.lingering)

        work.lingering.clear()

        late = await asyncio.gather(*lingering, return_exceptions=True)

        return list(results), list(late)

    def _cache_operation_build(self, rng: random.Random, present: set[str]) -> CacheOperation:
        name = rng.choice(CACHE_OPERATION_NAMES)

        if name == 'clear':
            if rng.random() < 0.7:
                name = 'get'

        if name == 'clear':
            return CacheOperation(name='clear')

        if name == 'many':
            keys = tuple(rng.sample(CACHE_KEYS, rng.randint(1, 3)))

            return CacheOperation(name='many', keys=keys)

        if name == 'incr':
            if not present:
                name = 'set'

        candidates = sorted(present) if name == 'incr' else CACHE_KEYS
        key = (rng.choice(candidates),)

        return CacheOperation(name=name, keys=key)

    def _cache_present_resync(self) -> None:
        self.model.cache_present = {key for key in CACHE_KEYS if cache.has_key(key)}

    def _client_ready(self) -> AsyncClient | Client:
        if self._client is None:
            message = 'the simulation client is used before it is set up'
            raise RuntimeError(message)

        return self._client

    def _get(self, run: Run, path: str, headers: dict[str, str] | None = None) -> HttpResponse:
        self.ledger.reset()

        with faults_installed(self.faults, run.rng, self.ledger):
            client = self._client_ready()

            if isinstance(client, AsyncClient):
                return async_get(client, path, headers=headers or {})

            return client.get(path, headers=headers or {})

    def _plan_build(self, run: Run, *, read_body: bool, route_async: bool) -> WorkPlan:
        rng = run.rng
        self._token_index += 1
        present = set(self.model.cache_present)
        operations = []

        for _ in range(rng.randint(0, 5)):
            operation = self._cache_operation_build(rng, present)

            cache_call_expected(operation, present)
            operations.append(operation)

        return WorkPlan(
            cache_operations=tuple(operations),
            distinct=rng.randint(1, 4),
            fail=rng.random() < 0.08,
            kind=rng.choice(self.kinds),
            queries=rng.randint(0, 8),
            read_body=read_body,
            status=rng.choice(STATUSES_WEIGHTED),
            templates=0 if route_async else rng.randint(0, 3),
            timing=rng.random() < 0.25,
            token=f'run-{run.seed % 10_000}-{self._token_index}',
        )

    def _post(self, run: Run, path: str, headers: dict[str, str]) -> HttpResponse:
        self.ledger.reset()

        with faults_installed(self.faults, run.rng, self.ledger):
            client = self._client_ready()

            if isinstance(client, AsyncClient):
                return async_post(client, path, data=FORM_FIELDS, headers=headers)

            return client.post(path, data=FORM_FIELDS, headers=headers)

    def _queries_captured_expected(self, outcome: _HostOutcome) -> int | None:
        if not outcome.visible:
            return None

        if not outcome.active['queries']:
            return None

        if not self.model.tracking(is_ajax=outcome.is_ajax):
            return None

        if self.ledger.panel_fired('queries', 'process_request', position='before'):
            return None

        if self.faults is not None:
            return self.ledger.statements_passed

        return outcome.plan.queries

    def _cache_data_check(self, data: dict) -> None:
        calls = [(call['method'], call['hit']) for call in data['calls']]
        hits = sum(1 for _, hit in calls if hit)

        check(len(calls) <= CACHE_CALLS_SIMULATED, f'cache calls exceed the bound: {len(calls)}')
        check(data['count'] == len(calls), 'the cache count disagrees with its calls')
        check(data['hits'] == hits, 'the cache hits disagree with its calls')

        if self.model.cache_calls is None:
            return

        check(
            calls == self.model.cache_calls,
            f'cache calls {calls!r} != model {self.model.cache_calls!r}',
        )

    def _data_check(self, panel_id: str, data: dict) -> None:
        checkers = {
            'cache': self._cache_data_check,
            'queries': self._queries_data_check,
            'request': self._request_data_check,
            'settings': self._settings_data_check,
            'signals': self._signals_data_check,
            'staticfiles': self._static_data_check,
            'templates': self._templates_data_check,
            'timer': self._timer_data_check,
        }

        checker = checkers.get(panel_id)

        if checker is not None:
            checker(data)

    def _host_body_check(self, outcome: _HostOutcome) -> None:
        plan = outcome.plan
        failed = plan.fail or outcome.view_faulted
        status_expected = 500 if failed else plan.status
        status = outcome.response.status_code

        check(
            status == status_expected,
            f'{outcome.path} answered {status}, expected {status_expected}',
        )

        if failed:
            check(
                shell_text().encode() not in outcome.content,
                f'{outcome.path} failed but carries the shell',
            )

            return

        expected = body_expected(plan, outcome.body_length)

        if outcome.visible:
            if injection_expected(plan, is_ajax=outcome.is_ajax):
                expected = body_injected(expected, charset_of(plan))

        check(
            outcome.content == expected,
            f'{outcome.path} body {outcome.content[:160]!r} != expected {expected[:160]!r}',
        )

    def _host_headers_check(self, outcome: _HostOutcome) -> None:
        response = outcome.response
        failed = outcome.plan.fail or outcome.view_faulted
        timing = response.get(HEADER_SERVER_TIMING, '')
        timing_view_expected = outcome.plan.timing and not failed
        timing_view = SERVER_TIMING_APPLICATION if timing_view_expected else ''

        if not outcome.visible:
            check(HEADER_REQUEST_ID not in response, 'a hidden request carries a request id')
            check(timing == timing_view, f'a hidden request changed Server-Timing: {timing!r}')

            return

        check(
            len(response.get(HEADER_REQUEST_ID, '')) == 32,
            'a visible request lacks a request id',
        )

        entries = server_timing_entries(timing) if timing else []

        if timing_view:
            check(
                entries[:1] == [timing_view],
                f'the view Server-Timing was not kept first: {timing!r}',
            )

        self._timing_metrics_check(outcome, entries)

        if response.has_header('Content-Length'):
            length = int(response['Content-Length'])

            check(length == len(outcome.content), 'Content-Length disagrees with the body')

    def _host_request(self, run: Run, *, hidden: bool, is_ajax: bool, method: str) -> _HostOutcome:
        route_async = self.asgi and run.rng.random() < ASYNC_ROUTE_CHANCE
        read_body = method == 'POST' and not route_async and run.rng.random() < 0.5
        plan = self._plan_build(run, read_body=read_body, route_async=route_async)
        headers = dict(run.rng.choice(HEADERS_AJAX if is_ajax else HEADERS_PAGE))

        if hidden:
            headers[HEADER_HIDDEN] = '1'

        active = {panel_id: self.model.active(panel_id) for panel_id in PANEL_IDS_DEFAULT}
        route = '/work-async/' if route_async else '/work/'
        path = f'{route}?{plan.query_string()}'
        body_length = 0

        if method == 'POST':
            response = self._post(run, path, headers)

            if read_body:
                body_length = len(encode_multipart(BOUNDARY, FORM_FIELDS))
        else:
            response = self._get(run, path, headers)

        outcome = _HostOutcome(
            active=active,
            body_length=body_length,
            content=_content_of(response),
            is_ajax=is_ajax,
            method=method,
            path=path,
            plan=plan,
            response=response,
            view=VIEW_ASYNC if route_async else VIEW_SYNC,
            view_faulted=self.ledger.any_fired('database') or self.ledger.any_fired('cache'),
            visible=not hidden,
        )

        status = response.status_code

        run.log(f'{method} {path} ajax={is_ajax} hidden={hidden} -> {status} {self.ledger.fired}')

        self._host_body_check(outcome)
        self._host_headers_check(outcome)
        self._model_update(outcome)
        self._host_sometimes(run, outcome)

        return outcome

    def _host_sometimes(self, run: Run, outcome: _HostOutcome) -> None:
        injected = shell_text().encode() in outcome.content
        captured = self._queries_captured_expected(outcome) is not None
        calls = self.model.cache_calls or []
        tracking = self.model.tracking(is_ajax=outcome.is_ajax)

        run.sometimes('ajax captured', condition=outcome.is_ajax and captured)
        run.sometimes('cache hit recorded', condition=any(hit for _, hit in calls))

        run.sometimes(
            'cache miss recorded',
            condition=any(method == 'GET' and not hit for method, hit in calls),
        )

        run.sometimes(
            'duplicates in one request',
            condition=outcome.plan.queries > outcome.plan.distinct,
        )

        run.sometimes('form body read by the view', condition=outcome.plan.read_body)

        run.sometimes(
            'isolation paused capture',
            condition=outcome.visible and self.model.isolated(),
        )

        run.sometimes('page injected', condition=injected)

        run.sometimes(
            'page not injected',
            condition=outcome.visible and not outcome.is_ajax and not injected,
        )

        run.sometimes(
            'store at capacity',
            condition=len(self.model.store) == REQUESTS_STORED_SIMULATED,
        )

        run.sometimes(
            'tracking skipped a request',
            condition=outcome.active['queries'] and not tracking,
        )

        profiled = outcome.active['profiling'] or outcome.active['line_profiling']
        page_async = outcome.view == VIEW_ASYNC and outcome.visible and not outcome.is_ajax

        run.sometimes('async page profiled', condition=page_async and profiled)
        run.sometimes('view failed', condition=outcome.plan.fail)
        run.sometimes(f'kind {outcome.plan.kind}', condition=not outcome.plan.fail)

    def _model_cache_update(self, outcome: _HostOutcome) -> None:
        calls: list[tuple[str, bool]] | None

        if self.ledger.any_fired('database'):
            calls = []
        elif self.ledger.any_fired('cache'):
            calls = None

            self._cache_present_resync()
        else:
            calls = cache_calls_expected(outcome.plan, self.model.cache_present)

        if not outcome.visible:
            return

        if not outcome.active['cache']:
            return

        if self.ledger.panel_fired('cache', 'process_request', position='before'):
            calls = []

        self.model.cache_calls_push(calls, is_ajax=outcome.is_ajax)

    def _model_page_update(self, outcome: _HostOutcome) -> None:
        page = PageExpectation(
            method=outcome.method,
            path=outcome.path,
            status_code=outcome.response.status_code,
            view=outcome.view,
        )

        if outcome.active['timer']:
            self.model.page_timer = page

        if outcome.active['request']:
            self.model.page_request = page

        if outcome.active['templates']:
            self._model_templates_update(outcome)

        if outcome.active['staticfiles']:
            self._model_static_update(outcome)

    def _model_static_update(self, outcome: _HostOutcome) -> None:
        response = outcome.response

        if getattr(response, 'streaming', False):
            return

        content_type = response.get('Content-Type', '').split(';')[0].strip().lower()

        if content_type not in HTML_TYPES:
            return

        content = outcome.content.replace(shell_text().encode(), b'', 1)
        self.model.static_used = static_used_expected(content, response.charset)

    def _model_templates_update(self, outcome: _HostOutcome) -> None:
        self.model.templates_seen = True

        if self.ledger.panel_fired('templates', 'process_request', position='before'):
            self.model.templates_count = 0
            self._templates_token = None

            return

        failed = outcome.plan.fail or outcome.view_faulted

        if failed:
            self.model.templates_count = None
            self._templates_token = None

            return

        self.model.templates_count = outcome.plan.templates
        self._templates_token = outcome.plan.token

    def _model_update(self, outcome: _HostOutcome) -> None:
        self._model_cache_update(outcome)

        if not outcome.visible:
            return

        count = self._queries_captured_expected(outcome)

        if count is not None:
            expectation = CapturedExpectation(
                is_ajax=outcome.is_ajax,
                method=outcome.method,
                path=outcome.path,
                query_count=count,
                status_code=outcome.response.status_code,
            )

            self.model.store_push(expectation, is_ajax=outcome.is_ajax)

        if not outcome.is_ajax:
            self._model_page_update(outcome)

    def _panel_data_fetch(self, run: Run, panel_id: str) -> None:
        response = self._get(run, f'{KALEIDOSCOPE_URL_PREFIX}panels/{panel_id}/data/')
        body = json_strict_load(response.content)

        if self.ledger.panel_fired(panel_id, 'get_data'):
            check(
                response.status_code == 500,
                f'{panel_id} data hid a fault: {response.status_code}',
            )

            return

        check(
            response.status_code == 200,
            f'{panel_id} data answered {response.status_code}: {body!r}',
        )

        check(isinstance(body, dict), f'{panel_id} data is not an object')

        self._data_check(panel_id, body)

    def _queries_data_check(self, data: dict) -> None:
        requests = data['requests']
        queries = [query for request in requests for query in request['queries']]
        counter = collections.Counter(query['sql'] for query in queries)
        duplicates = {sql: count for sql, count in counter.items() if count > 1}

        check(data['duplicates'] == duplicates, 'duplicates disagree with the stored queries')
        check(data['summary']['request_count'] == len(requests), 'the request count disagrees')
        check(data['summary']['total_queries'] == len(queries), 'the query total disagrees')
        check(len(requests) <= REQUESTS_STORED_SIMULATED, 'the store exceeds its bound')
        check(data['track_ajax'] is self.model.track_ajax, 'AJAX tracking disagrees with the model')
        check(data['track_page'] is self.model.track_page, 'page tracking disagrees with the model')

        for request in requests:
            check(
                request['query_count'] == len(request['queries']),
                'a request miscounts its queries',
            )

        for group in data['similar'].values():
            check(group['count'] > 1, 'a similar group holds a single query')

        if not self.model.store_known:
            return

        actual = [
            CapturedExpectation(
                is_ajax=request['is_ajax'],
                method=request['method'],
                path=request['path'],
                query_count=request['query_count'],
                status_code=request['status_code'],
            )
            for request in requests
        ]

        check(actual == self.model.store, f'queries store {actual!r} != model {self.model.store!r}')

    def _request_data_check(self, data: dict) -> None:
        page = self.model.page_request

        if page is None:
            check(data == {}, f'the request panel shows a page it never saw: {data!r}')

            return

        check(data['method'] == page.method, 'the request method disagrees')
        check(data['path'] == page.path, 'the request path disagrees')
        check(data['status_code'] == page.status_code, 'the request status disagrees')
        check(data['view']['func'] == page.view, 'the request view disagrees')

    def _settings_data_check(self, data: dict) -> None:
        text = json.dumps(data)

        for canary in CANARIES:
            check(canary not in text, f'the settings panel leaked {canary}')

        check(MASKED_VALUE in text, 'the settings panel masked nothing')

    def _signals_data_check(self, data: dict) -> None:
        sends = data['sends']
        durations = [send['duration_ms'] for send in sends]

        check(
            data['send_count'] >= sum(send['count'] for send in sends),
            'the send count is lower than its sends',
        )

        check(durations == sorted(durations, reverse=True), 'the sends are not slowest first')

    def _static_data_check(self, data: dict) -> None:
        if self.model.static_used is None:
            return

        check(
            data['used_files'] == self.model.static_used,
            f'static files {data["used_files"]!r} != model',
        )

    def _templates_data_check(self, data: dict) -> None:
        if not self.model.templates_seen:
            check(data == {}, f'the templates panel shows a page it never saw: {data!r}')

            return

        count = self.model.templates_count

        if count is None:
            return

        check(data['count'] == count, f'templates {data["count"]} != model {count}')
        check(len(data['templates']) == count, 'the template list disagrees with its count')

        for template in data['templates']:
            check(
                template['name'] == 'testapp/fragment.html',
                f'unexpected template {template["name"]}',
            )

            check(
                template['context_keys'] == ['index', 'token'],
                'unexpected template context keys',
            )

    def _timer_data_check(self, data: dict) -> None:
        page = self.model.page_timer

        if page is None:
            check(data == {}, f'the timer shows a page it never saw: {data!r}')

            return

        check(data['method'] == page.method, 'the timer method disagrees')
        check(data['path'] == page.path, 'the timer path disagrees')
        check(data['status_code'] == page.status_code, 'the timer status disagrees')
        check(data['asgi'] is self.asgi, 'the timer server kind disagrees')

    def _timing_metrics_check(self, outcome: _HostOutcome, entries: list[str]) -> None:
        count = self._queries_captured_expected(outcome)
        queries_entries = [entry for entry in entries if entry.startswith('queries_sql_count;')]
        queries_faulted = self.ledger.panel_fired('queries', 'get_server_timing')
        queries_expected = bool(count) and not queries_faulted

        if queries_expected:
            check(len(queries_entries) == 1, f'the query timing is missing: {entries!r}')

            check(
                queries_entries[0].endswith(f'desc="SQL {count} queries"'),
                f'the query timing miscounts: {queries_entries!r}',
            )
        else:
            check(not queries_entries, f'an unexpected query timing: {queries_entries!r}')

        timer_entries = [entry for entry in entries if entry.startswith('timer_total;')]
        timer_faulted = self.ledger.panel_fired('timer', 'get_server_timing')
        timer_expected = outcome.active['timer'] and not timer_faulted

        check(
            bool(timer_entries) is timer_expected,
            f'the timer timing presence is wrong: {entries!r}',
        )

    @classmethod
    def swarm(
        cls,
        rng: random.Random,
        *,
        asgi: bool = False,
        faults: Faults | None = None,
    ) -> tuple[ToolbarSimulation, tuple[Action, ...]]:
        kinds = swarmed(KINDS, rng)
        toggles = swarmed(TOGGLE_PANEL_IDS, rng)
        simulation = cls(asgi=asgi, faults=faults, kinds=kinds, toggles=toggles)
        actions = swarmed(simulation.actions(), rng)

        return simulation, actions

    @contextmanager
    def installed(self) -> Iterator[None]:
        patches = (
            mock.patch.object(store, 'REQUESTS_STORED_MAX', REQUESTS_STORED_SIMULATED),
            mock.patch.object(cache_panel, 'CACHE_CALLS_MAX', CACHE_CALLS_SIMULATED),
            mock.patch.object(injector, 'INJECTABLE_CONTENT_MAX', INJECTABLE_CONTENT_SIMULATED),
        )

        with ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)

            yield

    def setup(self, run: Run) -> None:
        cache.clear()

        for index in range(3):
            Author.objects.create(name=f'simulated-{index}')

        client_class = AsyncClient if self.asgi else Client
        self._client = client_class(raise_request_exception=False)

        for target in SOMETIMES_TARGETS:
            run.sometimes(target, condition=False)

        if self.asgi:
            for target in SOMETIMES_TARGETS_ASGI:
                run.sometimes(target, condition=False)

        run.log(f'setup asgi={self.asgi} kinds={self.kinds} toggles={self.toggles}')

    def actions(self) -> tuple[Action, ...]:
        weighted = (
            (self.ajax_request, 5),
            (self.form_post, 2),
            (self.hidden_request, 1),
            (self.ignored_request, 1),
            (self.page_request, 6),
            (self.toolbar_data, 4),
            (self.toolbar_garbage, 1),
            (self.toolbar_panels, 1),
            (self.toolbar_queries_action, 1),
            (self.toolbar_static, 1),
            (self.toolbar_template_value, 2),
            (self.toolbar_toggle, 2),
        )

        if self.asgi:
            weighted = (*weighted, (self.overlapping_requests, 2))

        return tuple(action for action, weight in weighted for _ in range(weight))

    def invariants(self) -> tuple[Action, ...]:
        return (
            self.invariant_hooks_clean,
            self.invariant_every_panel_answers,
            self.invariant_panels_match_model,
        )

    def ajax_request(self, run: Run) -> None:
        self._host_request(run, hidden=False, is_ajax=True, method='GET')

    def form_post(self, run: Run) -> None:
        self._host_request(run, hidden=False, is_ajax=run.rng.random() < 0.3, method='POST')

    def hidden_request(self, run: Run) -> None:
        outcome = self._host_request(run, hidden=True, is_ajax=run.rng.random() < 0.5, method='GET')

        run.sometimes(
            'hidden request untouched',
            condition=shell_text().encode() not in outcome.content,
        )

    def ignored_request(self, run: Run) -> None:
        headers = dict(run.rng.choice(HEADERS_PAGE + HEADERS_AJAX))
        response = self._get(run, '/ignored/', headers)

        check(response.status_code == 200, f'an ignored request answered {response.status_code}')
        check(response.content == PAGE_DOCUMENT.encode(), 'an ignored request was changed')
        check(HEADER_REQUEST_ID not in response, 'an ignored request carries a request id')

        run.sometimes('ignored request untouched')

    def invariant_every_panel_answers(self, run: Run) -> None:
        for panel_id in PANEL_IDS_DEFAULT:
            self._panel_data_fetch(run, panel_id)

    def invariant_hooks_clean(self, run: Run) -> None:
        _ = run

        for alias in connections:
            check(connections[alias].execute_wrappers == [], f'execute wrappers leaked on {alias}')

        check(cache_panel._collecting.get(None) is None, 'the cache collector stayed open')
        check(templates_panel._collecting.get(None) is None, 'the template collector stayed open')
        check(templates_panel._depth.get() == 0, 'the template depth stayed open')
        check(signals_panel._collecting.get(None) is None, 'the signal collector stayed open')
        check(signals_panel._depth.get() == 0, 'the signal depth stayed open')
        check(request_panel._checking.get(None) is None, 'the permission log stayed open')

        has_perm = vars(PermissionsMixin)['has_perm']

        if self.model.active('request'):
            check(is_patched(has_perm), 'has_perm is not wrapped while the request panel is active')

            check(
                not is_patched(has_perm.__wrapped__),
                'has_perm is wrapped twice while the request panel is active',
            )
        else:
            check(
                not is_patched(has_perm),
                'has_perm stayed wrapped while the request panel is inactive',
            )

        send = vars(django.dispatch.Signal)['send']

        if self.model.active('signals'):
            check(is_patched(send), 'Signal.send is not wrapped while the signals panel is active')

            check(
                not is_patched(send.__wrapped__),
                'Signal.send is wrapped twice while the signals panel is active',
            )
        else:
            check(
                not is_patched(send),
                'Signal.send stayed wrapped while the signals panel is inactive',
            )

        if self.model.active('templates'):
            check(
                is_patched(Template._render),
                'Template._render is not wrapped while the templates panel is active',
            )

            check(
                not is_patched(Template._render.__wrapped__),
                'Template._render is wrapped twice while the templates panel is active',
            )
        else:
            check(
                not is_patched(Template._render),
                'Template._render stayed wrapped while the templates panel is inactive',
            )

        if not self.model.active('cache'):
            check(
                len(cache_panel._caches_patched()) == 0,
                'a cache stayed patched while the cache panel is inactive',
            )

    def invariant_panels_match_model(self, run: Run) -> None:
        self.toolbar_panels(run)

    def overlapping_requests(self, run: Run) -> None:
        rng = run.rng
        plans = tuple(self._batch_plan_build(run) for _ in range(rng.choice(BATCH_SIZES)))
        cancel_index = rng.randrange(len(plans)) if rng.random() < BATCH_CANCEL_CHANCE else None
        cancel_turns = rng.randint(0, BATCH_CANCEL_TURNS_MAX)
        headers = dict(rng.choice(HEADERS_AJAX))
        batch_rng = random.Random(rng.getrandbits(64))
        active = {panel_id: self.model.active(panel_id) for panel_id in PANEL_IDS_DEFAULT}
        batch_run = async_to_sync(self._batch_run)

        self.ledger.reset()

        with faults_installed(self.faults, batch_rng, self.ledger):
            results, late = batch_run(
                plans,
                headers,
                cancel_index=cancel_index,
                cancel_turns=cancel_turns,
            )

        faulted = bool(self.ledger.fired)
        statuses = [getattr(result, 'status_code', type(result).__name__) for result in results]

        run.log(f'batch {[plan.token for plan in plans]} cancel={cancel_index} -> {statuses}')

        self._batch_check(run, plans, results, active=active, faulted=faulted)
        self._batch_model_update(active)

        run.sometimes(
            'late query while another request captured',
            condition=any(result is True for result in late),
        )

    def page_request(self, run: Run) -> None:
        self._host_request(run, hidden=False, is_ajax=False, method='GET')

    def toolbar_data(self, run: Run) -> None:
        panel_id = run.rng.choice(PANEL_IDS_DEFAULT)

        self._panel_data_fetch(run, panel_id)

    def toolbar_garbage(self, run: Run) -> None:
        path = run.rng.choice(PATHS_GARBAGE)
        response = self._get(run, f'{KALEIDOSCOPE_URL_PREFIX}{path}')

        check(
            response.status_code == 404,
            f'garbage toolbar path {path!r} answered {response.status_code}',
        )

        run.sometimes('toolbar garbage refused')

    def toolbar_panels(self, run: Run) -> None:
        response = self._get(run, f'{KALEIDOSCOPE_URL_PREFIX}panels/')

        check(response.status_code == 200, f'the panel list answered {response.status_code}')

        panels = json_strict_load(response.content)['panels']
        identifiers = tuple(panel['id'] for panel in panels)

        check(identifiers == PANEL_IDS_DEFAULT, f'the panel list changed: {identifiers!r}')

        for panel in panels:
            enabled = self.model.panels_enabled[panel['id']]

            check(panel['enabled'] is enabled, f'{panel["id"]} enabled disagrees with the model')
            check(isinstance(panel['summary'], str), f'{panel["id"]} summary is not text')

            if self.ledger.panel_fired(panel['id'], 'get_summary'):
                check(panel['summary'] == '', f'{panel["id"]} summary hid a fault')

    def toolbar_queries_action(self, run: Run) -> None:
        action = run.rng.choice(QUERY_ACTIONS)
        response = self._get(run, f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/action/{action}/')

        check(
            response.status_code == 200,
            f'queries action {action} answered {response.status_code}',
        )

        match action:
            case 'clear':
                self.model.store.clear()
                self.model.store_known = True

                run.sometimes('queries action clear')
            case 'track-ajax-off':
                self.model.track_ajax = False
            case 'track-ajax-on':
                self.model.track_ajax = True
            case 'track-page-off':
                self.model.track_page = False
            case _:
                self.model.track_page = True

    def toolbar_static(self, run: Run) -> None:
        filename, status = run.rng.choice(STATIC_FILES)
        response = self._get(run, f'{KALEIDOSCOPE_URL_PREFIX}static/{filename}')

        check(response.status_code == status, f'static {filename} answered {response.status_code}')

        run.sometimes('toolbar static served', condition=status == 200)

    def toolbar_template_value(self, run: Run) -> None:
        path = run.rng.choice(TEMPLATE_VALUE_PATHS)
        index = run.rng.choice(TEMPLATE_VALUE_INDEXES)
        query = urlencode({'path': path, 'template': index})

        response = self._get(
            run,
            f'{KALEIDOSCOPE_URL_PREFIX}panels/templates/action/value/?{query}',
        )

        status = response.status_code
        body = json_strict_load(response.content)

        check(status in {200, 400, 404}, f'template value answered {status}')

        count = self.model.templates_count
        token = self._templates_token
        known = path == TEMPLATE_VALUE_PATHS[0] and index.isdigit() and count is not None
        resolvable = known and token is not None and int(index) < count

        if resolvable:
            check(status == 200, f'template value of a known token answered {status}')
            check(body['value']['value'] == token, f'template value {body!r} != {token!r}')

        run.sometimes(f'template value {status}')

    def toolbar_toggle(self, run: Run) -> None:
        panel_id = run.rng.choice(self.toggles)
        enabled = not self.model.panels_enabled[panel_id]

        if panel_id in PANEL_IDS_ISOLATED:
            if enabled:
                if run.rng.random() < 0.6:
                    return

        action = 'enable' if enabled else 'disable'
        response = self._get(run, f'{KALEIDOSCOPE_URL_PREFIX}panels/{panel_id}/{action}/')

        check(response.status_code == 200, f'{action} {panel_id} answered {response.status_code}')

        check(
            json_strict_load(response.content) == {'enabled': enabled},
            f'{action} {panel_id} disagrees',
        )

        self.model.enabled_set(panel_id, enabled=enabled)

        run.log(f'panel {panel_id} {action}d, isolated={self.model.isolated()}')
