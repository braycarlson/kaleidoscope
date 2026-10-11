from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import sys
import threading

import pytest

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync, sync_to_async
from django.core.cache import cache
from django.db import connection, connections
from django.http import HttpResponse
from django.template import Context, Template
from django.test import AsyncRequestFactory, RequestFactory

from kaleidoscope.middleware import KaleidoscopeMiddleware
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

    from django.http import HttpRequest


HEADERS_AJAX = MappingProxyType({
    'HTTP_ACCEPT': 'application/json',
    'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest',
})

HEADERS_PAGE = MappingProxyType({'HTTP_ACCEPT': 'text/html'})
READER_ROUNDS_MAX = 10_000
REQUESTS_PER_WORKER = 40
SEED = 20261010
SHELL = b'<div id="ks-app"'
SWITCH_INTERVAL_S = 1e-6
TOKEN = re.compile(r'w\d+r\d+')
WORKERS = 8


@dataclass(frozen=True)
class Work:
    ajax: bool
    cache_calls: int
    queries: int
    templates: int
    token: str


class Toolbar:
    def __init__(self, plans: dict[str, Work]) -> None:
        view = _view_build(plans)
        self.factory = RequestFactory()
        self.middleware = KaleidoscopeMiddleware(view)
        self.plans = plans

    def _panel_read(self, panel_id: str) -> dict:
        request = self.factory.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/{panel_id}/data/')
        response = self.middleware(request)

        assert response.status_code == 200

        return json.loads(response.content)

    def request_run(self, work: Work) -> None:
        headers = HEADERS_AJAX if work.ajax else HEADERS_PAGE
        response = self.middleware(self.factory.get(f'/stress/{work.token}/', **headers))
        server_timing = response.get('Server-Timing', '')

        assert response.status_code == 200
        assert (f'desc="SQL {work.queries} queries"' in server_timing) is (work.queries > 0)
        assert (SHELL in response.content) is not work.ajax
        assert not any(connections[alias].execute_wrappers for alias in connections)

    def snapshot_check(self) -> None:
        self._cache_check(self._panel_read('cache')['calls'])
        self._queries_check(self._panel_read('queries')['requests'])
        self._templates_check(self._panel_read('templates'))

    def _cache_check(self, calls: list[dict]) -> None:
        tokens = [TOKEN.search(call['args']).group(0) for call in calls]
        pages = {token for token in tokens if not self.plans[token].ajax}

        assert len(pages) <= 1

        for token in set(tokens):
            assert tokens.count(token) == self.plans[token].cache_calls

    def _queries_check(self, records: list[dict]) -> None:
        for record in records:
            work = self.plans[record['path'].strip('/').split('/')[-1]]

            assert record['is_ajax'] is work.ajax
            assert record['query_count'] == work.queries
            assert all(work.token in query['sql'] for query in record['queries'])

    def _templates_check(self, data: dict) -> None:
        names = {template['name'] for template in data.get('templates', [])}

        assert len(names) <= 1

        for name in names:
            assert data.get('count') == self.plans[name].templates
            assert not self.plans[name].ajax


def _plans_build(rng: random.Random) -> dict[str, Work]:
    plans = {}

    for worker in range(WORKERS):
        for index in range(REQUESTS_PER_WORKER):
            token = f'w{worker}r{index}'

            plans[token] = Work(
                ajax=rng.random() < 0.5,
                cache_calls=rng.randint(0, 3),
                queries=rng.randint(0, 4),
                templates=rng.randint(0, 3),
                token=token,
            )

    return plans


def _query_run(token: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute('SELECT %s', [token])


def _view_async_build(plans: dict[str, Work]) -> Callable[[HttpRequest], Awaitable[HttpResponse]]:
    async def view(request: HttpRequest) -> HttpResponse:
        work = plans[request.path.strip('/').split('/')[-1]]

        for _ in range(work.queries):
            await sync_to_async(_query_run)(work.token)
            await asyncio.sleep(0)

        for _ in range(work.templates):
            context = Context({'token': work.token})
            template = Template('{{ token }}', name=work.token)

            template.render(context)
            await asyncio.sleep(0)

        if work.ajax:
            return HttpResponse('{}', content_type='application/json')

        return HttpResponse(f'<html><body>{work.token}</body></html>', content_type='text/html')

    return view


async def _asgi_requests_run(plans: dict[str, Work]) -> list[dict]:
    view = _view_async_build(plans)
    middleware = KaleidoscopeMiddleware(view)
    factory = AsyncRequestFactory()

    async def request_run(work: Work) -> None:
        accept = 'application/json' if work.ajax else 'text/html'
        request = factory.get(f'/stress/{work.token}/', headers={'Accept': accept})
        response = await middleware(request)
        server_timing = response.get('Server-Timing', '')

        assert response.status_code == 200
        assert (f'desc="SQL {work.queries} queries"' in server_timing) is (work.queries > 0)

    await asyncio.gather(*(request_run(work) for work in plans.values()))

    response = await middleware(factory.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/data/'))

    return json.loads(response.content)['requests']


def _view_build(plans: dict[str, Work]) -> Callable[[HttpRequest], HttpResponse]:
    def view(request: HttpRequest) -> HttpResponse:
        work = plans[request.path.strip('/').split('/')[-1]]

        with connection.cursor() as cursor:
            for _ in range(work.queries):
                cursor.execute('SELECT %s', [work.token])

        for _ in range(work.templates):
            context = Context({'token': work.token})
            template = Template('{{ token }}', name=work.token)

            template.render(context)

        for index in range(work.cache_calls):
            cache.set(f'{work.token}:{index}', index)

        if work.ajax:
            return HttpResponse('{}', content_type='application/json')

        return HttpResponse(f'<html><body>{work.token}</body></html>', content_type='text/html')

    return view


def _snapshots_checked(toolbar: Toolbar, finished: threading.Event) -> int:
    for rounds in range(READER_ROUNDS_MAX):
        if finished.is_set():
            return rounds

        toolbar.snapshot_check()

    return READER_ROUNDS_MAX


def _thread_connections_close() -> None:
    for alias in connections:
        handle = connections[alias].connection

        if handle is not None:
            handle.close()


@pytest.fixture
def switching_fast() -> Iterator[None]:
    interval = sys.getswitchinterval()

    sys.setswitchinterval(SWITCH_INTERVAL_S)

    yield

    sys.setswitchinterval(interval)


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures('switching_fast')
def test_concurrent_requests_never_mix_their_records(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)

    rng = random.Random(SEED)
    plans = _plans_build(rng)
    toolbar = Toolbar(plans)
    barrier = threading.Barrier(WORKERS + 1)
    finished = threading.Event()

    def worker(index: int) -> None:
        barrier.wait()

        try:
            for request in range(REQUESTS_PER_WORKER):
                toolbar.request_run(toolbar.plans[f'w{index}r{request}'])
        finally:
            _thread_connections_close()

    def reader() -> int:
        barrier.wait()

        try:
            rounds = _snapshots_checked(toolbar, finished)
        finally:
            _thread_connections_close()

        return rounds

    with ThreadPoolExecutor(max_workers=WORKERS + 1) as executor:
        reading = executor.submit(reader)
        workers = [executor.submit(worker, index) for index in range(WORKERS)]

        try:
            for future in workers:
                future.result()
        finally:
            finished.set()

        rounds = reading.result()

    toolbar.snapshot_check()

    assert rounds > 0
    assert [record.getMessage() for record in caplog.records] == []


@pytest.mark.django_db(transaction=True)
def test_interleaved_asgi_requests_on_one_thread_keep_their_own_queries() -> None:
    rng = random.Random(SEED)
    plans = _plans_build(rng)
    records = async_to_sync(_asgi_requests_run)(plans)

    assert records

    for record in records:
        work = plans[record['path'].strip('/').split('/')[-1]]

        assert record['query_count'] == work.queries
        assert all(work.token in query['sql'] for query in record['queries'])
