from __future__ import annotations

import functools
import linecache
import logging
import reprlib
import sys
import sysconfig
import threading
import time

from collections import Counter, deque
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from django.db import connections
from django.template.base import Node, TokenType
from sqlparse import tokens
from sqlparse.lexer import tokenize

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import FrameType
    from typing import Any, Callable


QUERIES_PER_REQUEST_MAX = 10_000
QUERY_PARAMS_LENGTH_MAX = 10_000
QUERY_SQL_LENGTH_MAX = 100_000
REQUESTS_STORED_MAX = 200
STACK_DEPTH_MAX = 10_000
STACK_FRAMES_MAX = 256
STATUS_CODE_MAX = 599
STATUS_CODE_MIN = 100
TEMPLATE_FRAMES_MAX = 64
TEMPLATE_TEXT_LENGTH_MAX = 200
TEXT_TRUNCATED_SUFFIX = '...'
_FROZEN_PREFIX = '<frozen '
_KALEIDOSCOPE_PATH = Path(__file__).parent.as_posix() + '/'
_LIBRARY_DIRECTORIES = ('/dist-packages/', '/site-packages/')
_LIBRARY_PATH_KEYS = ('platlib', 'platstdlib', 'purelib', 'stdlib')
_NORMALIZED_CACHE_LENGTH_MAX = 4_096
_NORMALIZED_CACHE_SIZE = 1_024
_NUMBER_TYPES = (tokens.Literal.Number.Float, tokens.Literal.Number.Integer)
_PARAMS_CONTAINER_ITEMS_MAX = 100
_PARAMS_ITEM_LENGTH_MAX = 1_000
_RENDER_ANNOTATED_CODE = Node.render_annotated.__code__
_USER_FRAME_CACHE_SIZE = 4_096
_capture_active: ContextVar[QueryCapture | None] = ContextVar('_capture_active', default=None)

logger = logging.getLogger(__name__)


def _dispatcher_find(wrappers: list) -> CaptureDispatcher | None:
    if not isinstance(wrappers, list):
        message = f'execute wrappers must be a list: {wrappers!r}'
        raise TypeError(message)

    for wrapper in wrappers:
        if isinstance(wrapper, CaptureDispatcher):
            return wrapper

    return None


@functools.cache
def _frames_foreign_prefixes() -> tuple[str, ...]:
    paths = sysconfig.get_paths()
    prefixes = {_KALEIDOSCOPE_PATH}

    for key in _LIBRARY_PATH_KEYS:
        directory = paths[key].replace('\\', '/').rstrip('/')

        if not directory:
            message = f'sysconfig names an empty {key} directory, which would hide every frame'
            raise RuntimeError(message)

        prefixes.add(directory + '/')

    return tuple(sorted(prefixes))


def _is_literal(token_type: tuple) -> bool:
    if not isinstance(token_type, tuple):
        message = f'a token type must be a tuple: {token_type!r}'
        raise TypeError(message)

    if token_type in tokens.Literal.String.Single:
        return True

    return token_type in _NUMBER_TYPES


@functools.lru_cache(maxsize=_USER_FRAME_CACHE_SIZE)
def _is_user_frame(filename: str) -> bool:
    if not isinstance(filename, str):
        message = f'a frame filename must be text: {filename!r}'
        raise TypeError(message)

    path = filename.replace('\\', '/')

    if path.startswith(_FROZEN_PREFIX):
        return False

    for directory in _LIBRARY_DIRECTORIES:
        if directory in path:
            return False

    return not path.startswith(_frames_foreign_prefixes())


@functools.cache
def _params_reprlib() -> reprlib.Repr:
    instance = reprlib.Repr()
    instance.maxarray = _PARAMS_CONTAINER_ITEMS_MAX
    instance.maxdeque = _PARAMS_CONTAINER_ITEMS_MAX
    instance.maxdict = _PARAMS_CONTAINER_ITEMS_MAX
    instance.maxfrozenset = _PARAMS_CONTAINER_ITEMS_MAX
    instance.maxlist = _PARAMS_CONTAINER_ITEMS_MAX
    instance.maxlong = _PARAMS_ITEM_LENGTH_MAX
    instance.maxother = _PARAMS_ITEM_LENGTH_MAX
    instance.maxset = _PARAMS_CONTAINER_ITEMS_MAX
    instance.maxstring = _PARAMS_ITEM_LENGTH_MAX
    instance.maxtuple = _PARAMS_CONTAINER_ITEMS_MAX

    return instance


def _params_text(params: Any) -> str | None:
    if params is None:
        return None

    if isinstance(params, (dict, list, tuple)):
        if not params:
            return None

    text = _params_reprlib().repr(params)

    return _text_bounded(text, QUERY_PARAMS_LENGTH_MAX)


def _queries_listed(
    queries: list[dict],
    *,
    stacks: dict[tuple, list[dict]],
    templates: dict[tuple, list[dict]],
) -> list[dict]:
    if not isinstance(queries, list):
        message = f'queries must be a list: {queries!r}'
        raise TypeError(message)

    if not isinstance(stacks, dict):
        message = f'stacks must be a dict: {stacks!r}'
        raise TypeError(message)

    if not isinstance(templates, dict):
        message = f'templates must be a dict: {templates!r}'
        raise TypeError(message)

    listed = []

    for query in queries:
        stack = query['stack']
        template_stack = query['templates']

        if not isinstance(stack, tuple):
            message = f'a stored stack must be a tuple of frames: {stack!r}'
            raise TypeError(message)

        if not isinstance(template_stack, tuple):
            message = f'a stored template stack must be a tuple of frames: {template_stack!r}'
            raise TypeError(message)

        frames = stacks.get(stack)

        if frames is None:
            frames = _stack_listed(stack)
            stacks[stack] = frames

        template_frames = templates.get(template_stack)

        if template_frames is None:
            template_frames = _templates_listed(template_stack)
            templates[template_stack] = template_frames

        entry = {**query, 'stack': frames, 'templates': template_frames}

        listed.append(entry)

    return listed


def _query_record(
    sql: str,
    params: Any,
    *,
    context: dict,
    duration_ns: int,
    many: bool,
    stack: tuple,
    templates: tuple,
) -> dict:
    if not isinstance(context, dict):
        message = f'an execute context must be a dict: {context!r}'
        raise TypeError(message)

    if not isinstance(duration_ns, int):
        message = f'duration_ns must be an integer: {duration_ns!r}'
        raise TypeError(message)

    if duration_ns < 0:
        message = f'duration_ns must not be negative: {duration_ns}'
        raise ValueError(message)

    if not isinstance(many, bool):
        message = f'many must be a bool: {many!r}'
        raise TypeError(message)

    if not isinstance(stack, tuple):
        message = f'a stack must be a tuple of frames: {stack!r}'
        raise TypeError(message)

    if not isinstance(templates, tuple):
        message = f'templates must be a tuple of template frames: {templates!r}'
        raise TypeError(message)

    connection = context.get('connection')
    formatted = _sql_formatted(context, sql, params)

    return {
        'alias': getattr(connection, 'alias', 'default'),
        'many': many,
        'params': _params_text(params),
        'raw_sql': _text_bounded(str(sql), QUERY_SQL_LENGTH_MAX),
        'rows': _rows_counted(context),
        'sql': _text_bounded(formatted, QUERY_SQL_LENGTH_MAX),
        'stack': stack,
        'templates': templates,
        'time': duration_ns / 1_000_000_000,
    }


def _rows_counted(context: dict) -> int | None:
    if not isinstance(context, dict):
        message = f'an execute context must be a dict: {context!r}'
        raise TypeError(message)

    try:
        rows = getattr(context.get('cursor'), 'rowcount', None)
    except Exception:
        rows = None

    if isinstance(rows, bool):
        return None

    if not isinstance(rows, int):
        return None

    if rows < 0:
        return None

    return rows


def _sql_formatted(context: dict, sql: str, params: Any) -> str:
    try:
        formatted = context['connection'].ops.last_executed_query(context['cursor'], sql, params)
    except Exception:
        formatted = None

    if isinstance(formatted, str):
        return formatted

    return str(sql)


def _sql_normalized(sql: str) -> str:
    if not isinstance(sql, str):
        message = f'a statement to normalize must be text: {sql!r}'
        raise TypeError(message)

    if len(sql) <= _NORMALIZED_CACHE_LENGTH_MAX:
        return _sql_normalized_cached(sql)

    return _sql_normalized_uncached(sql)


@functools.lru_cache(maxsize=_NORMALIZED_CACHE_SIZE)
def _sql_normalized_cached(sql: str) -> str:
    return _sql_normalized_uncached(sql)


def _sql_normalized_uncached(sql: str) -> str:
    parts: list[str] = []

    for token_type, value in tokenize(sql):
        if _is_literal(token_type):
            parts.append('%s')
        elif token_type in tokens.Whitespace:
            if parts:
                if parts[-1] == ' ':
                    continue

            parts.append(' ')
        else:
            parts.append(value)

    return ''.join(parts)


def _stack_extract() -> tuple[tuple[tuple[str, str, int], ...], tuple[tuple[str, int, str], ...]]:
    frames = []
    templates = []
    frame = sys._getframe()

    for _ in range(STACK_DEPTH_MAX):
        if frame is None:
            break

        if len(frames) >= STACK_FRAMES_MAX:
            break

        code = frame.f_code

        if code is _RENDER_ANNOTATED_CODE:
            template = _template_frame(frame)

            if template is not None:
                if len(templates) < TEMPLATE_FRAMES_MAX:
                    templates.append(template)
        elif _is_user_frame(code.co_filename):
            entry = (code.co_filename, code.co_name, frame.f_lineno)

            frames.append(entry)

        frame = frame.f_back

    frames.reverse()
    templates.reverse()

    return tuple(frames), tuple(templates)


def _stack_listed(stack: tuple[tuple[str, str, int], ...]) -> list[dict]:
    if len(stack) > STACK_FRAMES_MAX:
        message = f'a stack holds at most {STACK_FRAMES_MAX} frames, not {len(stack)}'
        raise ValueError(message)

    return [
        {
            'file': filename,
            'function': function,
            'line': line,
            'text': linecache.getline(filename, line).strip(),
        }
        for filename, function, line in stack
    ]


def _template_frame(frame: FrameType) -> tuple[str, int, str] | None:
    node = frame.f_locals.get('self')
    origin = getattr(node, 'origin', None)
    token = getattr(node, 'token', None)

    if origin is None:
        return None

    if token is None:
        return None

    name = getattr(origin, 'template_name', None) or getattr(origin, 'name', '')
    line = getattr(token, 'lineno', None)

    if not isinstance(line, int):
        line = 0

    return (str(name), line, _token_text(token))


def _templates_listed(templates: tuple[tuple[str, int, str], ...]) -> list[dict]:
    if len(templates) > TEMPLATE_FRAMES_MAX:
        message = f'a template stack holds {len(templates)} frames, over {TEMPLATE_FRAMES_MAX}'
        raise ValueError(message)

    return [{'line': line, 'name': name, 'text': text} for name, line, text in templates]


def _text_bounded(text: str, length_max: int) -> str:
    if not isinstance(text, str):
        message = f'text to bound must be text: {text!r}'
        raise TypeError(message)

    if length_max < 1:
        message = f'length_max must be positive: {length_max}'
        raise ValueError(message)

    if len(text) <= length_max:
        return text

    return text[:length_max] + TEXT_TRUNCATED_SUFFIX


def _token_text(token: object) -> str:
    contents = str(getattr(token, 'contents', ''))
    token_type = getattr(token, 'token_type', None)

    if token_type is TokenType.VAR:
        text = '{{ ' + contents + ' }}'
    elif token_type is TokenType.BLOCK:
        text = '{% ' + contents + ' %}'
    else:
        text = contents

    return _text_bounded(text, TEMPLATE_TEXT_LENGTH_MAX)


def user_frame_innermost() -> dict | None:
    stack, _ = _stack_extract()

    if not stack:
        return None

    return _stack_listed(stack[-1:])[0]


class CaptureDispatcher:
    def __init__(self) -> None:
        self.depth = 0

    def __call__(self, execute: Callable, sql: str, params: Any, many: bool, context: dict) -> Any:
        capture = _capture_active.get()

        if capture is None:
            return execute(sql, params, many, context)

        return capture(execute, sql, params, many, context)


class QueryCapture:
    def __init__(self) -> None:
        self._detached = False
        self._previous: QueryCapture | None = None
        self._stacks: dict[tuple, tuple] = {}
        self.queries: list[dict] = []

    def __call__(
        self,
        execute: Callable,
        sql: str,
        params: Any,
        many: bool,
        context: dict,
    ) -> Any:
        if self._detached:
            return execute(sql, params, many, context)

        started_ns = time.perf_counter_ns()

        try:
            result = execute(sql, params, many, context)
        finally:
            duration_ns = time.perf_counter_ns() - started_ns

            self._record(sql, params, context=context, duration_ns=duration_ns, many=many)

        return result

    def _record(
        self,
        sql: str,
        params: Any,
        *,
        context: dict,
        duration_ns: int,
        many: bool,
    ) -> None:
        if len(self.queries) >= QUERIES_PER_REQUEST_MAX:
            return

        try:
            stack, templates = _stack_extract()

            query = _query_record(
                sql,
                params,
                context=context,
                duration_ns=duration_ns,
                many=many,
                stack=self._stacks.setdefault(stack, stack),
                templates=self._stacks.setdefault(templates, templates),
            )
        except Exception:
            logger.exception('Kaleidoscope could not record a query')
        else:
            self.queries.append(query)

    def attach(self) -> None:
        if self._detached:
            message = 'a detached capture cannot attach again'
            raise RuntimeError(message)

        previous = _capture_active.get()

        if previous is self:
            message = 'a capture cannot attach twice'
            raise RuntimeError(message)

        self._previous = previous

        _capture_active.set(self)

        for alias in connections:
            wrappers = connections[alias].execute_wrappers
            dispatcher = _dispatcher_find(wrappers)

            if dispatcher is None:
                dispatcher = CaptureDispatcher()
                wrappers.append(dispatcher)

            dispatcher.depth += 1

    def detach(self) -> None:
        if _capture_active.get() is self:
            _capture_active.set(self._previous)

        if self._detached:
            return

        self._detached = True

        for alias in connections:
            wrappers = connections[alias].execute_wrappers
            dispatcher = _dispatcher_find(wrappers)

            if dispatcher is None:
                continue

            if dispatcher.depth < 1:
                message = f'the dispatcher on {alias!r} was detached more often than attached'
                raise RuntimeError(message)

            dispatcher.depth -= 1

            if dispatcher.depth <= 0:
                wrappers.remove(dispatcher)


@dataclass
class CapturedRequest:
    duration: float
    is_ajax: bool
    method: str
    path: str
    queries: list[dict]
    query_count: int
    query_time: float
    request_id: str
    status_code: int
    timestamp: float

    def __post_init__(self) -> None:
        if not _is_number(self.duration):
            message = f'duration must be a number: {self.duration!r}'
            raise TypeError(message)

        if self.duration < 0:
            message = f'duration must not be negative: {self.duration}'
            raise ValueError(message)

        if not isinstance(self.is_ajax, bool):
            message = f'is_ajax must be a bool: {self.is_ajax!r}'
            raise TypeError(message)

        if not isinstance(self.method, str):
            message = f'method must be text: {self.method!r}'
            raise TypeError(message)

        if not self.method:
            message = 'method must not be empty'
            raise ValueError(message)

        if not isinstance(self.path, str):
            message = f'path must be text: {self.path!r}'
            raise TypeError(message)

        if not isinstance(self.queries, list):
            message = f'queries must be a list: {self.queries!r}'
            raise TypeError(message)

        if self.query_count != len(self.queries):
            message = f'query_count {self.query_count!r} disagrees with {len(self.queries)} queries'
            raise ValueError(message)

        if not _is_number(self.query_time):
            message = f'query_time must be a number: {self.query_time!r}'
            raise TypeError(message)

        if self.query_time < 0:
            message = f'query_time must not be negative: {self.query_time}'
            raise ValueError(message)

        self._request_id_validate()
        self._status_validate()

        if not _is_number(self.timestamp):
            message = f'timestamp must be a number: {self.timestamp!r}'
            raise TypeError(message)

    def _request_id_validate(self) -> None:
        if not isinstance(self.request_id, str):
            message = f'request_id must be text: {self.request_id!r}'
            raise TypeError(message)

        if not self.request_id:
            message = 'request_id must not be empty'
            raise ValueError(message)

    def _status_validate(self) -> None:
        if isinstance(self.status_code, bool):
            message = f'status_code must be an integer, not a bool: {self.status_code!r}'
            raise TypeError(message)

        if not isinstance(self.status_code, int):
            message = f'status_code must be an integer: {self.status_code!r}'
            raise TypeError(message)

        if self.status_code < STATUS_CODE_MIN:
            message = f'status_code must be at least {STATUS_CODE_MIN}: {self.status_code}'
            raise ValueError(message)

        if self.status_code > STATUS_CODE_MAX:
            message = f'status_code must be at most {STATUS_CODE_MAX}: {self.status_code}'
            raise ValueError(message)


def _duplicates(queries: list[dict]) -> dict[str, int]:
    if not isinstance(queries, list):
        message = f'queries must be a list: {queries!r}'
        raise TypeError(message)

    counter = Counter(query.get('sql', '') for query in queries)
    return {sql: count for sql, count in counter.items() if count > 1}


def _is_number(value: object) -> bool:
    if isinstance(value, bool):
        return False

    return isinstance(value, (int, float))


def _similar_groups(queries: list[dict]) -> dict[str, dict]:
    if not isinstance(queries, list):
        message = f'queries must be a list: {queries!r}'
        raise TypeError(message)

    groups: dict[str, dict] = {}

    for query in queries:
        sql = query.get('sql', '')
        normalized = _sql_normalized(query.get('raw_sql') or sql)

        if normalized not in groups:
            groups[normalized] = {'count': 0, 'example': sql, 'total_time': 0.0}

        groups[normalized]['count'] += 1
        groups[normalized]['total_time'] += float(query.get('time', 0)) * 1000

    return {normalized: group for normalized, group in groups.items() if group['count'] > 1}


def _summary(requests: Iterable[CapturedRequest]) -> dict:
    query_count = 0
    query_time = 0.0
    request_count = 0

    for captured in requests:
        if not isinstance(captured, CapturedRequest):
            message = f'a summary covers captured requests, not {type(captured).__name__}'
            raise TypeError(message)

        query_count += captured.query_count
        query_time += captured.query_time
        request_count += 1

    return {
        'request_count': request_count,
        'total_queries': query_count,
        'total_query_time': round(query_time, 2),
    }


class QueryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: deque[CapturedRequest] = deque(maxlen=REQUESTS_STORED_MAX)

    @property
    def data(self) -> dict:
        with self._lock:
            requests = list(self._requests)

        queries: list[dict] = []
        stacks: dict[tuple, list[dict]] = {}
        templates: dict[tuple, list[dict]] = {}

        for captured in requests:
            queries.extend(captured.queries)

        return {
            'duplicates': _duplicates(queries),
            'requests': [
                {
                    'duration': captured.duration,
                    'is_ajax': captured.is_ajax,
                    'method': captured.method,
                    'path': captured.path,
                    'queries': _queries_listed(
                        captured.queries,
                        stacks=stacks,
                        templates=templates,
                    ),
                    'query_count': captured.query_count,
                    'query_time': captured.query_time,
                    'request_id': captured.request_id,
                    'status_code': captured.status_code,
                    'timestamp': captured.timestamp,
                }
                for captured in requests
            ],
            'similar': _similar_groups(queries),
            'summary': _summary(requests),
        }

    @property
    def summary(self) -> dict:
        with self._lock:
            return _summary(self._requests)

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()

    def push(self, request: CapturedRequest) -> None:
        if not isinstance(request, CapturedRequest):
            message = f'the store holds captured requests, not {type(request).__name__}'
            raise TypeError(message)

        with self._lock:
            if not request.is_ajax:
                self._requests.clear()

            self._requests.append(request)

    def request_find(self, request_id: str) -> CapturedRequest | None:
        if not isinstance(request_id, str):
            message = f'request_id must be text: {request_id!r}'
            raise TypeError(message)

        with self._lock:
            requests = list(self._requests)

        for captured in requests:
            if captured.request_id == request_id:
                return captured

        return None
