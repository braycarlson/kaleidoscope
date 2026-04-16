from __future__ import annotations

import threading
import time
import traceback

from collections import Counter, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from kaleidoscope.constants import (
    QUERIES_PER_REQUEST_MAX,
    REQUESTS_STORED_MAX,
    STACK_FRAMES_MAX,
    KALEIDOSCOPE_URL_PREFIX,
)

if TYPE_CHECKING:
    from typing import Any, Callable

    from kaleidoscope.normalizer import SqlNormalizer


_KALEIDOSCOPE_PATH = KALEIDOSCOPE_URL_PREFIX.strip('/').replace('\\', '/')


class QueryCapture:
    def __init__(self) -> None:
        self.queries: list[dict] = []

    def __call__(
        self,
        execute: Callable,
        sql: str,
        params: Any,
        many: bool,
        context: dict,
    ) -> Any:
        start = time.perf_counter_ns()

        try:
            result = execute(sql, params, many, context)
        finally:
            try:
                duration_ns = time.perf_counter_ns() - start

                if len(self.queries) < QUERIES_PER_REQUEST_MAX:
                    stack = traceback.extract_stack()

                    filtered_stack = [
                        {
                            'file': frame.filename,
                            'function': frame.name,
                            'line': frame.lineno,
                            'text': frame.line or '',
                        }
                        for frame in stack
                        if '/site-packages/' not in frame.filename
                        and _KALEIDOSCOPE_PATH not in frame.filename.replace('\\', '/')
                    ][:STACK_FRAMES_MAX]

                    try:
                        connection = context['connection']
                        formatted = connection.ops.last_executed_query(
                            context['cursor'], sql, params,
                        )
                    except (KeyError, TypeError, ValueError, AttributeError):
                        formatted = sql

                    self.queries.append({
                        'sql': formatted,
                        'raw_sql': sql,
                        'params': repr(params) if params else None,
                        'many': many,
                        'stack': filtered_stack,
                        'time': duration_ns / 1_000_000_000,
                    })
            except Exception:
                pass

        return result


@dataclass
class CapturedRequest:
    duration: float
    is_ajax: bool
    method: str
    path: str
    queries: list[dict]
    query_count: int
    query_time: float
    status_code: int
    timestamp: float


class QueryStore:
    def __init__(self, sql_normalizer: SqlNormalizer) -> None:
        self._lock = threading.Lock()
        self._page_timestamp: float = 0.0
        self._requests: deque[CapturedRequest] = deque(maxlen=REQUESTS_STORED_MAX)
        self._sql_normalizer = sql_normalizer

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()
            self._page_timestamp = 0.0

    def _build_duplicates(self, all_queries: list[dict]) -> dict[str, int]:
        sql_counter = Counter(query.get('sql', '') for query in all_queries)

        return {
            sql: count
            for sql, count in sql_counter.items()
            if count > 1
        }

    def _build_similar_groups(self, all_queries: list[dict]) -> dict[str, dict]:
        groups: dict[str, dict] = {}

        for query in all_queries:
            sql = query.get('sql', '')
            normalized = self._sql_normalizer.normalize(sql)

            if normalized not in groups:
                groups[normalized] = {
                    'count': 0,
                    'example': sql,
                    'total_time': 0.0,
                }

            groups[normalized]['count'] += 1
            groups[normalized]['total_time'] += float(query.get('time', 0)) * 1000

        return {
            normalized: group
            for normalized, group in groups.items()
            if group['count'] > 1
        }

    @property
    def data(self) -> dict:
        with self._lock:
            requests = list(self._requests)

        all_queries: list[dict] = []

        for captured in requests:
            all_queries.extend(captured.queries)

        duplicates = self._build_duplicates(all_queries)
        similar = self._build_similar_groups(all_queries)

        total_queries = sum(captured.query_count for captured in requests)
        total_query_time = sum(captured.query_time for captured in requests)

        return {
            'duplicates': duplicates,
            'requests': [
                {
                    'duration': captured.duration,
                    'is_ajax': captured.is_ajax,
                    'method': captured.method,
                    'path': captured.path,
                    'queries': captured.queries,
                    'query_count': captured.query_count,
                    'query_time': captured.query_time,
                    'status_code': captured.status_code,
                    'timestamp': captured.timestamp,
                }
                for captured in requests
            ],
            'similar': similar,
            'summary': {
                'request_count': len(requests),
                'total_queries': total_queries,
                'total_query_time': round(total_query_time, 2),
            },
        }

    @property
    def summary(self) -> dict:
        with self._lock:
            total_queries = sum(
                captured.query_count for captured in self._requests
            )

            total_query_time = sum(
                captured.query_time for captured in self._requests
            )

            return {
                'request_count': len(self._requests),
                'total_queries': total_queries,
                'total_query_time': round(total_query_time, 2),
            }

    def push(self, request: CapturedRequest) -> None:
        with self._lock:
            if not request.is_ajax:
                self._requests.clear()
                self._page_timestamp = time.time()

            self._requests.append(request)
