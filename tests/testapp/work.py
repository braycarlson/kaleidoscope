from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import time

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, StreamingHttpResponse
from django.template.loader import render_to_string

from tests.testapp.models import Author

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.http import QueryDict


CACHE_KEY_CHARACTERS = frozenset('abcdefghijklmnopqrstuvwxyz')
CACHE_KEY_LENGTH_MAX = 8
CACHE_MANY_KEYS_MAX = 4
CACHE_OPERATION_NAMES = ('add', 'clear', 'del', 'get', 'getd', 'gos', 'has', 'incr', 'many', 'set')
CACHE_OPERATIONS_MAX = 12
CACHE_VALUE = 1
CACHE_VALUE_FALLBACK = 'fallback'
DISTINCT_MAX = 10

KINDS = (
    'binary',
    'empty',
    'gzip',
    'html',
    'html_bare',
    'html_upper',
    'invalid',
    'json',
    'large',
    'latin1',
    'mislabeled',
    'stream',
    'text',
    'xhtml',
)

LARGE_PADDING_BYTES = 12_288
LINGER_MAX = 8
QUERIES_MAX = 40
SERVER_TIMING_APPLICATION = 'app;dur=1.5;desc="app"'
SPIN_MS = 30
SPIN_TURNS_MAX = 100_000_000
STATUSES = (200, 201, 302, 404, 500)
STREAM_CHUNK_COUNT = 3
TEMPLATES_MAX = 5
TOKEN_CHARACTERS = frozenset('abcdefghijklmnopqrstuvwxyz0123456789-')
TOKEN_LENGTH_MAX = 32
lingering: list[asyncio.Future] = []


class WorkFailedError(Exception):
    """An exception that is raised when a work plan asks its view to fail."""


class WorkPlanError(ValueError):
    """An exception that is raised when a work plan carries a value outside its bounds."""


@dataclass(frozen=True)
class CacheOperation:
    name: str
    keys: tuple[str, ...] = ()

    def encode(self) -> str:
        if not self.keys:
            return self.name

        return f'{self.name}:{".".join(self.keys)}'


@dataclass(frozen=True)
class WorkPlan:
    cache_operations: tuple[CacheOperation, ...] = ()
    distinct: int = 1
    fail: bool = False
    kind: str = 'html'
    linger: int = 0
    queries: int = 0
    read_body: bool = False
    status: int = 200
    templates: int = 0
    timing: bool = False
    token: str = 'token'

    def __post_init__(self) -> None:
        _plan_validate(self)

    @classmethod
    def parse(cls, data: QueryDict) -> WorkPlan:
        encoded = data.get('cache', '')
        operations = tuple(_cache_operation_parse(part) for part in encoded.split(',') if part)

        return cls(
            cache_operations=operations,
            distinct=_integer_parse(data, 'distinct', default=1),
            fail=data.get('fail') == '1',
            kind=data.get('kind', 'html'),
            linger=_integer_parse(data, 'linger', default=0),
            queries=_integer_parse(data, 'queries', default=0),
            read_body=data.get('read_body') == '1',
            status=_integer_parse(data, 'status', default=200),
            templates=_integer_parse(data, 'templates', default=0),
            timing=data.get('timing') == '1',
            token=data.get('token', 'token'),
        )

    def query_string(self) -> str:
        cache_encoded = ','.join(operation.encode() for operation in self.cache_operations)

        parameters = {
            'cache': cache_encoded,
            'distinct': self.distinct,
            'fail': int(self.fail),
            'kind': self.kind,
            'linger': self.linger,
            'queries': self.queries,
            'read_body': int(self.read_body),
            'status': self.status,
            'templates': self.templates,
            'timing': int(self.timing),
            'token': self.token,
        }

        return urlencode(parameters)


def _cache_operation_parse(encoded: str) -> CacheOperation:
    name, _, keys_encoded = encoded.partition(':')
    keys = tuple(key for key in keys_encoded.split('.') if key)
    operation = CacheOperation(name=name, keys=keys)

    _cache_operation_validate(operation)

    return operation


def _cache_operation_validate(operation: CacheOperation) -> None:
    if operation.name not in CACHE_OPERATION_NAMES:
        message = f'unknown cache operation: {operation.name!r}'
        raise WorkPlanError(message)

    if operation.name == 'clear':
        if operation.keys:
            message = f'clear takes no keys: {operation.keys!r}'
            raise WorkPlanError(message)

        return

    key_count_max = CACHE_MANY_KEYS_MAX if operation.name == 'many' else 1

    if not operation.keys:
        message = f'{operation.name} needs a key'
        raise WorkPlanError(message)

    if len(operation.keys) > key_count_max:
        message = f'{operation.name} takes at most {key_count_max} keys: {operation.keys!r}'
        raise WorkPlanError(message)

    for key in operation.keys:
        _cache_key_validate(key)


def _cache_key_validate(key: str) -> None:
    if not key:
        message = 'cache key must not be empty'
        raise WorkPlanError(message)

    if len(key) > CACHE_KEY_LENGTH_MAX:
        message = f'cache key exceeds {CACHE_KEY_LENGTH_MAX} characters: {key!r}'
        raise WorkPlanError(message)

    if not set(key) <= CACHE_KEY_CHARACTERS:
        message = f'cache key must be lowercase letters: {key!r}'
        raise WorkPlanError(message)


def _integer_parse(data: QueryDict, name: str, *, default: int) -> int:
    raw = data.get(name, '')

    if not raw:
        return default

    if not raw.isascii():
        message = f'{name} must be a non-negative integer: {raw!r}'
        raise WorkPlanError(message)

    if not raw.isdigit():
        message = f'{name} must be a non-negative integer: {raw!r}'
        raise WorkPlanError(message)

    return int(raw)


def _plan_validate(plan: WorkPlan) -> None:
    if len(plan.cache_operations) > CACHE_OPERATIONS_MAX:
        message = f'cache operations exceed {CACHE_OPERATIONS_MAX}: {len(plan.cache_operations)}'
        raise WorkPlanError(message)

    if plan.distinct < 1:
        message = f'distinct must be at least one: {plan.distinct}'
        raise WorkPlanError(message)

    if plan.distinct > DISTINCT_MAX:
        message = f'distinct exceeds {DISTINCT_MAX}: {plan.distinct}'
        raise WorkPlanError(message)

    if plan.kind not in KINDS:
        message = f'unknown kind: {plan.kind!r}'
        raise WorkPlanError(message)

    if plan.linger > LINGER_MAX:
        message = f'linger exceeds {LINGER_MAX}: {plan.linger}'
        raise WorkPlanError(message)

    if plan.queries > QUERIES_MAX:
        message = f'queries exceed {QUERIES_MAX}: {plan.queries}'
        raise WorkPlanError(message)

    if plan.status not in STATUSES:
        message = f'unknown status: {plan.status}'
        raise WorkPlanError(message)

    if plan.templates > TEMPLATES_MAX:
        message = f'templates exceed {TEMPLATES_MAX}: {plan.templates}'
        raise WorkPlanError(message)

    _token_validate(plan.token)


def _token_validate(token: str) -> None:
    if not token:
        message = 'token must not be empty'
        raise WorkPlanError(message)

    if len(token) > TOKEN_LENGTH_MAX:
        message = f'token exceeds {TOKEN_LENGTH_MAX} characters: {token!r}'
        raise WorkPlanError(message)

    if not set(token) <= TOKEN_CHARACTERS:
        message = f'token must be lowercase letters, digits, and hyphens: {token!r}'
        raise WorkPlanError(message)


def cache_operation_run(operation: CacheOperation) -> None:
    key = operation.keys[0] if operation.keys else ''

    match operation.name:
        case 'add':
            cache.add(key, CACHE_VALUE)
        case 'clear':
            cache.clear()
        case 'del':
            cache.delete(key)
        case 'get':
            cache.get(key)
        case 'getd':
            cache.get(key, CACHE_VALUE_FALLBACK)
        case 'gos':
            cache.get_or_set(key, CACHE_VALUE)
        case 'has':
            cache.has_key(key)
        case 'incr':
            cache.incr(key)
        case 'many':
            cache.get_many(list(operation.keys))
        case 'set':
            cache.set(key, CACHE_VALUE)
        case _:
            message = f'unknown cache operation: {operation.name!r}'
            raise WorkPlanError(message)


def document_build(plan: WorkPlan, fragments: str, body_length: int) -> str:
    body_open = '<BODY>' if plan.kind == 'html_upper' else '<body>'
    body_close = '</body>'

    if plan.kind == 'html_upper':
        body_close = '</BODY>'

    if plan.kind == 'html_bare':
        body_close = ''

    padding = 'x' * LARGE_PADDING_BYTES if plan.kind == 'large' else ''
    accent = 'café' if plan.kind == 'latin1' else ''

    return (
        '<!DOCTYPE html><html><head>'
        f'<title>{plan.token}</title>'
        '<link rel="stylesheet" href="/static/testapp/site.css">'
        '<script src="/static/testapp/vendor/static/app.js"></script>'
        f'</head>{body_open}<main>{fragments}<p>{plan.token} {body_length}{accent}</p>'
        f'{padding}</main>{body_close}</html>'
    )


def fragments_render(plan: WorkPlan) -> str:
    rendered = [
        render_to_string('testapp/fragment.html', {'index': index, 'token': plan.token})
        for index in range(plan.templates)
    ]

    return ''.join(rendered)


def queries_run(plan: WorkPlan) -> None:
    for index in range(plan.queries):
        query_run(plan, index)


def query_late_run(plan: WorkPlan) -> bool:
    captured_elsewhere = bool(connection.execute_wrappers)

    query_run(plan, 0)

    return captured_elsewhere


async def query_lingering(plan: WorkPlan) -> bool:
    for _ in range(plan.linger):
        await asyncio.sleep(0)

    return await sync_to_async(query_late_run)(plan)


def query_run(plan: WorkPlan, index: int) -> None:
    Author.objects.filter(pk=index % plan.distinct + 1).first()


def response_build(plan: WorkPlan, fragments: str, body_length: int) -> HttpResponse:
    content_type = response_content_type(plan)
    content = response_content(plan, fragments, body_length)

    if plan.kind == 'stream':
        chunks = _stream_chunks(content)
        response = StreamingHttpResponse(chunks, content_type=content_type, status=plan.status)
    else:
        response = HttpResponse(content, content_type=content_type, status=plan.status)

    if plan.kind == 'gzip':
        response['Content-Encoding'] = 'gzip'

    if plan.timing:
        response['Server-Timing'] = SERVER_TIMING_APPLICATION

    return response


def response_content(plan: WorkPlan, fragments: str, body_length: int) -> bytes:
    document = document_build(plan, fragments, body_length)

    if plan.kind == 'binary':
        digest = hashlib.sha256(plan.token.encode()).digest()

        return digest * 4

    if plan.kind == 'empty':
        return b''

    if plan.kind == 'gzip':
        return gzip.compress(document.encode(), mtime=0)

    if plan.kind == 'invalid':
        return document.encode().replace(b'<main>', b'<main>\xff\xfe', 1)

    if plan.kind == 'json':
        payload = {'body_length': body_length, 'templates': plan.templates, 'token': plan.token}

        return json.dumps(payload, sort_keys=True).encode()

    if plan.kind == 'latin1':
        return document.encode('iso-8859-1')

    if plan.kind == 'text':
        return f'{plan.token} {body_length}'.encode()

    return document.encode()


def response_content_type(plan: WorkPlan) -> str:
    content_types = {
        'binary': 'application/octet-stream',
        'json': 'application/json',
        'latin1': 'text/html; charset=iso-8859-1',
        'mislabeled': 'text/html; charset=undefined',
        'text': 'text/plain; charset=utf-8',
        'xhtml': 'application/xhtml+xml; charset=utf-8',
    }

    return content_types.get(plan.kind, 'text/html; charset=utf-8')


def spin_for_profile(milliseconds: int) -> int:
    deadline_ns = time.perf_counter_ns() + milliseconds * 1_000_000

    for turn in range(SPIN_TURNS_MAX):
        if time.perf_counter_ns() >= deadline_ns:
            return turn

    return SPIN_TURNS_MAX


def _stream_chunks(content: bytes) -> Iterator[bytes]:
    size = -(-len(content) // STREAM_CHUNK_COUNT) or 1

    for start in range(0, len(content), size):
        yield content[start:start + size]
