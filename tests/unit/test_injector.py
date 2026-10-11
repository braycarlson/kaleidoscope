from __future__ import annotations

import codecs
import gzip
import os
import re

import pytest

from types import SimpleNamespace
from typing import TYPE_CHECKING

from django.http import HttpResponse, StreamingHttpResponse

from kaleidoscope import injector
from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.injector import (
    ENVIRONMENT_LAUNCH,
    INJECTABLE_CONTENT_MAX,
    HEADER_REQUEST_ID,
    HEADER_SERVER_TIMING,
    ResponseInjector,
    is_html_response,
    launch_token,
    server_timing_entry,
)
from kaleidoscope.panel import Panel, ServerTimingMetric

from tests.toolbar import shell_text

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from django.test import RequestFactory


CODEC_DECODE_ONLY = 'kaleidoscope-decode-only'
DOCUMENT = '<html><head></head><body><p>content</p></body></html>'
PATTERN_NOTHING = re.compile(r'(?!)')


class _TimingPanel(Panel):
    panel_id = 'probe'
    title = 'Probe'

    def __init__(self, metrics: list[ServerTimingMetric]) -> None:
        super().__init__()

        self.metrics = metrics

    def get_data(self) -> dict:
        return {}

    def get_server_timing(self, context: KaleidoscopeContext) -> list[ServerTimingMetric]:
        _ = context

        return self.metrics

    def get_summary(self) -> str:
        return ''


class _TimingPanelMalformed(_TimingPanel):
    panel_id = 'malformed'


class _TimingPanelBroken(_TimingPanel):
    panel_id = 'broken'

    def get_server_timing(self, context: KaleidoscopeContext) -> list[ServerTimingMetric]:
        _ = context
        message = 'timing is broken'

        raise RuntimeError(message)


def _codec_decode_only_encode(text: str, errors: str = 'strict') -> tuple[bytes, int]:
    _ = errors
    message = 'this codec only decodes'

    raise UnicodeEncodeError(CODEC_DECODE_ONLY, text, 0, len(text), message)


def _codec_decode_only_decode(data: bytes, errors: str = 'strict') -> tuple[str, int]:
    return bytes(data).decode('utf-8', errors), len(data)


def _codec_decode_only_find(name: str) -> codecs.CodecInfo | None:
    if name != CODEC_DECODE_ONLY.replace('-', '_'):
        return None

    return codecs.CodecInfo(
        _codec_decode_only_encode,
        _codec_decode_only_decode,
        name=CODEC_DECODE_ONLY,
    )


@pytest.fixture
def codec_decode_only() -> Iterator[str]:
    codecs.register(_codec_decode_only_find)

    yield CODEC_DECODE_ONLY

    codecs.unregister(_codec_decode_only_find)


def _context_build(
    *,
    is_ajax: bool = False,
    panels: list[Panel] | None = None,
) -> KaleidoscopeContext:
    return KaleidoscopeContext(is_ajax=is_ajax, panels=panels or [], request_id='0' * 32)


def _processed(
    request_factory: RequestFactory,
    response: HttpResponse,
    *,
    is_ajax: bool = False,
) -> HttpResponse:
    request = request_factory.get('/')
    context = _context_build(is_ajax=is_ajax)

    return ResponseInjector().process(request, response, context)


def test_shell_goes_immediately_before_the_closing_body_tag(
    request_factory: RequestFactory,
) -> None:
    response = HttpResponse(DOCUMENT)
    content = _processed(request_factory, response).content.decode()

    assert content == DOCUMENT.replace('</body>', shell_text() + '</body>')
    assert int(response['Content-Length']) == len(response.content)


def test_shell_goes_before_the_last_closing_body_tag(request_factory: RequestFactory) -> None:
    document = '<html><body><pre>&lt;/body&gt; </body> inside</pre></body></html>'
    response = HttpResponse(document)
    content = _processed(request_factory, response).content.decode()
    expected = f'<html><body><pre>&lt;/body&gt; </body> inside</pre>{shell_text()}</body></html>'

    assert content == expected


@pytest.mark.parametrize('closing', ['</BODY>', '</Body>', '</body >', '</body\n>'])
def test_shell_finds_a_closing_body_tag_in_any_case_or_spacing(
    request_factory: RequestFactory,
    closing: str,
) -> None:
    document = f'<html><body><p>content</p>{closing}</html>'
    response = HttpResponse(document)
    content = _processed(request_factory, response).content.decode()

    assert content == document.replace(closing, shell_text() + closing)


def test_document_without_a_closing_body_tag_is_left_alone(request_factory: RequestFactory) -> None:
    document = '<html><body><p>content</p></html>'
    response = HttpResponse(document)

    assert _processed(request_factory, response).content.decode() == document


def test_document_already_carrying_the_toolbar_is_left_alone(
    request_factory: RequestFactory,
) -> None:
    document = DOCUMENT.replace('</body>', shell_text() + '</body>')
    response = HttpResponse(document)

    assert _processed(request_factory, response).content.decode() == document


@pytest.mark.parametrize(
    'content_type',
    ['text/html', 'text/html; charset=utf-8', 'TEXT/HTML', 'application/xhtml+xml'],
)
def test_every_html_content_type_is_injected(
    request_factory: RequestFactory,
    content_type: str,
) -> None:
    response = HttpResponse(DOCUMENT, content_type=content_type)
    content = _processed(request_factory, response).content.decode()

    assert content.count(shell_text()) == 1


@pytest.mark.parametrize(
    'content_type',
    ['application/json', 'text/plain', 'text/css', 'application/octet-stream', ''],
)
def test_non_html_content_is_left_alone(request_factory: RequestFactory, content_type: str) -> None:
    response = HttpResponse(DOCUMENT, content_type=content_type)

    assert _processed(request_factory, response).content.decode() == DOCUMENT


@pytest.mark.parametrize('status', [199, 204, 205, 206, 301, 302, 304, 400, 404, 500, 503])
def test_responses_outside_two_hundred_are_left_alone(
    request_factory: RequestFactory,
    status: int,
) -> None:
    response = HttpResponse(DOCUMENT, status=status)

    assert _processed(request_factory, response).content.decode() == DOCUMENT


def test_ajax_responses_are_left_alone(request_factory: RequestFactory) -> None:
    response = HttpResponse(DOCUMENT)

    assert _processed(request_factory, response, is_ajax=True).content.decode() == DOCUMENT


def test_streaming_responses_are_left_alone(request_factory: RequestFactory) -> None:
    chunks = [DOCUMENT.encode()]
    response = StreamingHttpResponse(chunks, content_type='text/html')
    processed = _processed(request_factory, response)

    assert b''.join(processed.streaming_content) == DOCUMENT.encode()


def test_encoded_responses_are_left_alone(request_factory: RequestFactory) -> None:
    compressed = gzip.compress(DOCUMENT.encode(), mtime=0)
    response = HttpResponse(compressed)
    response['Content-Encoding'] = 'gzip'

    assert _processed(request_factory, response).content == compressed


def test_oversized_documents_are_left_alone(request_factory: RequestFactory) -> None:
    padding = 'x' * INJECTABLE_CONTENT_MAX
    document = f'<html><body>{padding}</body></html>'
    response = HttpResponse(document)

    assert _processed(request_factory, response).content == document.encode()


def test_bytes_that_do_not_decode_in_the_declared_charset_are_left_alone(
    request_factory: RequestFactory,
) -> None:
    content = b'<html><body>\xff\xfe broken</body></html>'
    response = HttpResponse(content, content_type='text/html; charset=utf-8')

    assert _processed(request_factory, response).content == content


@pytest.mark.parametrize('charset', ['no-such-charset', 'undefined'])
def test_an_unknown_or_unusable_charset_is_left_alone(
    request_factory: RequestFactory,
    charset: str,
) -> None:
    content = DOCUMENT.encode()
    response = HttpResponse(content, content_type=f'text/html; charset={charset}')

    assert _processed(request_factory, response).content == content


def test_a_latin_one_document_is_injected_and_stays_latin_one(
    request_factory: RequestFactory,
) -> None:
    document = '<html><body>café</body></html>'
    content = document.encode('iso-8859-1')
    response = HttpResponse(content, content_type='text/html; charset=iso-8859-1')
    processed = _processed(request_factory, response).content

    assert processed.decode('iso-8859-1') == document.replace('</body>', shell_text() + '</body>')


def test_the_request_id_header_is_always_set(request_factory: RequestFactory) -> None:
    response = HttpResponse('{}', content_type='application/json')

    assert _processed(request_factory, response, is_ajax=True)[HEADER_REQUEST_ID] == '0' * 32


@pytest.mark.parametrize('attribute', ['_csp_nonce', 'csp_nonce'])
def test_the_shell_script_carries_the_csp_nonce(
    request_factory: RequestFactory,
    attribute: str,
) -> None:
    request = request_factory.get('/')

    setattr(request, attribute, 'n0nce-value')
    response = HttpResponse(DOCUMENT)
    context = _context_build()
    content = ResponseInjector().process(request, response, context).content.decode()

    assert '<script nonce="n0nce-value" type="module"' in content


def test_the_csp_nonce_is_escaped_inside_the_attribute(request_factory: RequestFactory) -> None:
    request = request_factory.get('/')
    request.csp_nonce = 'abc" onload="alert(1)'
    response = HttpResponse(DOCUMENT)
    context = _context_build()
    content = ResponseInjector().process(request, response, context).content.decode()

    assert 'onload="alert(1)"' not in content
    assert 'nonce="abc&quot; onload=&quot;alert(1)"' in content


def test_the_shell_host_carries_the_launch_token_escaped(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    monkeypatch.setenv(ENVIRONMENT_LAUNCH, 'launch" onload="alert(1)')

    request = request_factory.get('/')
    response = HttpResponse(DOCUMENT)
    context = _context_build()
    content = ResponseInjector().process(request, response, context).content.decode()

    assert 'onload="alert(1)"' not in content
    assert '<div id="ks-app" data-launch="launch&quot; onload=&quot;alert(1)"></div>' in content


def test_a_launch_token_is_made_once_and_kept_for_the_processes_it_spawns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENVIRONMENT_LAUNCH, raising=False)

    token = launch_token()

    assert re.fullmatch('[0-9a-f]{32}', token)
    assert launch_token() == token
    assert os.environ[ENVIRONMENT_LAUNCH] == token


def test_server_timing_lists_each_metric_of_each_panel(request_factory: RequestFactory) -> None:
    metrics = [
        ServerTimingMetric(key='first', description='First', duration=1.234),
        ServerTimingMetric(key='second', description='Second', duration=5),
    ]

    panel = _TimingPanel(metrics)
    context = _context_build(panels=[panel])
    request = request_factory.get('/')
    response = HttpResponse('{}', content_type='application/json')
    header = ResponseInjector().process(request, response, context)[HEADER_SERVER_TIMING]

    assert header == 'probe_first;dur=1.23;desc="First", probe_second;dur=5.00;desc="Second"'


def test_server_timing_survives_a_panel_whose_timing_raises(
    request_factory: RequestFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    metrics = [ServerTimingMetric(key='ok', description='Ok', duration=1.0)]
    panels = [_TimingPanelBroken(metrics), _TimingPanel(metrics)]
    context = _context_build(panels=panels)
    request = request_factory.get('/')
    response = HttpResponse(DOCUMENT)
    processed = ResponseInjector().process(request, response, context)

    assert processed[HEADER_SERVER_TIMING] == 'probe_ok;dur=1.00;desc="Ok"'
    assert processed.content.decode().count(shell_text()) == 1
    assert 'broken' in caplog.text


def test_server_timing_is_absent_when_no_panel_reports(request_factory: RequestFactory) -> None:
    response = HttpResponse(DOCUMENT)

    assert HEADER_SERVER_TIMING not in _processed(request_factory, response)


@pytest.mark.parametrize(
    ('name', 'duration', 'description', 'expected'),
    [
        ('queries_sql', 1.5, 'SQL 3 queries', 'queries_sql;dur=1.50;desc="SQL 3 queries"'),
        ('a b', 1.0, 'd', 'a_b;dur=1.00;desc="d"'),
        ('x', 2.0, 'say "hi"', 'x;dur=2.00;desc="say \\"hi\\""'),
        ('x', 2.0, 'back\\slash', 'x;dur=2.00;desc="back\\\\slash"'),
        ('x', 2.0, 'line\r\nbreak', 'x;dur=2.00;desc="line  break"'),
        ('x', float('nan'), 'd', None),
        ('x', float('inf'), 'd', None),
        ('', 1.0, 'd', None),
    ],
)
def test_server_timing_entry_is_always_a_valid_header_fragment(
    name: str,
    duration: float,
    description: str,
    expected: str | None,
) -> None:
    assert server_timing_entry(name, duration, description) == expected


def test_server_timing_with_a_newline_never_breaks_the_response(
    request_factory: RequestFactory,
) -> None:
    metrics = [ServerTimingMetric(key='bad\nkey', description='bad\ndescription', duration=1.0)]
    panel = _TimingPanel(metrics)
    context = _context_build(panels=[panel])
    request = request_factory.get('/')
    response = HttpResponse(DOCUMENT)
    header = ResponseInjector().process(request, response, context)[HEADER_SERVER_TIMING]

    assert '\n' not in header
    assert header == 'probe_bad_key;dur=1.00;desc="bad description"'


@pytest.mark.parametrize(
    'metrics',
    [
        None,
        [None],
        [SimpleNamespace(key='bad', description='d', duration='slow')],
        [SimpleNamespace(key='bad', description=None, duration=1.0)],
        [ServerTimingMetric(key='bad', description='d', duration=10**400)],
    ],
)
def test_server_timing_skips_a_panel_that_reports_malformed_metrics(
    request_factory: RequestFactory,
    metrics: list[ServerTimingMetric],
    caplog: pytest.LogCaptureFixture,
) -> None:
    valid = [ServerTimingMetric(key='ok', description='Ok', duration=1.0)]
    panels = [_TimingPanelMalformed(metrics), _TimingPanel(valid)]
    context = _context_build(panels=panels)
    request = request_factory.get('/')
    response = HttpResponse(DOCUMENT)
    processed = ResponseInjector().process(request, response, context)

    assert processed[HEADER_SERVER_TIMING] == 'probe_ok;dur=1.00;desc="Ok"'
    assert processed.content.decode().count(shell_text()) == 1
    assert 'malformed' in caplog.text


def test_a_charset_that_decodes_but_cannot_encode_is_left_alone(
    request_factory: RequestFactory,
    codec_decode_only: str,
) -> None:
    content = DOCUMENT.encode()
    response = HttpResponse(content, content_type=f'text/html; charset={codec_decode_only}')

    assert _processed(request_factory, response).content == content


def test_server_timing_drops_a_metric_whose_duration_is_not_finite(
    request_factory: RequestFactory,
) -> None:
    metrics = [
        ServerTimingMetric(key='nan', description='d', duration=float('nan')),
        ServerTimingMetric(key='ok', description='Ok', duration=2.0),
    ]

    panel = _TimingPanel(metrics)
    context = _context_build(panels=[panel])
    request = request_factory.get('/')
    response = HttpResponse(DOCUMENT)
    header = ResponseInjector().process(request, response, context)[HEADER_SERVER_TIMING]

    assert header == 'probe_ok;dur=2.00;desc="Ok"'


def test_a_django_csp_nonce_is_carried_only_once_the_page_generated_it(
    request_factory: RequestFactory,
) -> None:
    csp = pytest.importorskip('django.utils.csp')
    request_unused = request_factory.get('/')
    request_used = request_factory.get('/')
    request_unused._csp_nonce = csp.LazyNonce()
    request_used._csp_nonce = csp.LazyNonce()
    nonce = str(request_used._csp_nonce)
    injector = ResponseInjector()
    response_unused = HttpResponse(DOCUMENT)
    response_used = HttpResponse(DOCUMENT)
    unused = injector.process(request_unused, response_unused, _context_build()).content.decode()
    used = injector.process(request_used, response_used, _context_build()).content.decode()

    assert 'nonce=' not in unused
    assert not request_unused._csp_nonce
    assert f'<script nonce="{nonce}" type="module"' in used


def test_processing_refuses_arguments_of_the_wrong_kind(request_factory: RequestFactory) -> None:
    request = request_factory.get('/')
    response = HttpResponse(DOCUMENT)
    context = _context_build()
    response_injector = ResponseInjector()

    with pytest.raises(TypeError, match='request must be an HttpRequest: dict'):
        response_injector.process({}, response, context)  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='response must be an HttpResponseBase: str'):
        response_injector.process(request, DOCUMENT, context)  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='context must be a KaleidoscopeContext: dict'):
        response_injector.process(request, response, {})  # ty:ignore[invalid-argument-type]


def test_processing_refuses_a_context_holding_something_other_than_a_panel(
    request_factory: RequestFactory,
) -> None:
    context = KaleidoscopeContext(panels=[object()], request_id='0' * 32)
    request = request_factory.get('/')

    with pytest.raises(TypeError, match='the context holds a object among its panels'):
        ResponseInjector().process(request, HttpResponse(DOCUMENT), context)


def test_html_detection_refuses_something_that_is_not_a_response() -> None:
    with pytest.raises(TypeError, match='response must be an HttpResponseBase: NoneType'):
        is_html_response(None)  # ty:ignore[invalid-argument-type]


def test_server_timing_names_the_panel_that_reports_something_other_than_a_metric(
    request_factory: RequestFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    valid = [ServerTimingMetric(key='ok', description='Ok', duration=1.0)]
    malformed = _TimingPanelMalformed(['slow'])  # ty:ignore[invalid-argument-type]
    context = _context_build(panels=[malformed, _TimingPanel(valid)])
    request = request_factory.get('/')
    processed = ResponseInjector().process(request, HttpResponse(DOCUMENT), context)

    assert processed[HEADER_SERVER_TIMING] == 'probe_ok;dur=1.00;desc="Ok"'
    assert 'the malformed panel reported a str instead of a ServerTimingMetric' in caplog.text


@pytest.mark.parametrize(
    ('arguments', 'pattern'),
    [
        ((7, 1.0, 'd'), 'name must be text: 7'),
        (('x', True, 'd'), 'duration must be a number, not a bool: True'),
        (('x', '1.0', 'd'), "duration must be a number: '1.0'"),
        (('x', 1.0, None), 'description must be text: None'),
    ],
)
def test_server_timing_entry_refuses_arguments_of_the_wrong_kind(
    arguments: tuple,
    pattern: str,
) -> None:
    with pytest.raises(TypeError, match=pattern):
        server_timing_entry(*arguments)


@pytest.mark.parametrize(
    ('name', 'pattern'),
    [
        ('caf\u00e9', 'must be ascii'),
        ('a\nb', 'must not carry control characters'),
    ],
)
def test_server_timing_entry_never_returns_an_unsafe_header_fragment(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    pattern: str,
) -> None:
    monkeypatch.setattr(injector, '_TOKEN_UNSAFE_PATTERN', PATTERN_NOTHING)

    with pytest.raises(RuntimeError, match=pattern):
        server_timing_entry(name, 1.0, 'd')


@pytest.mark.parametrize(
    ('shell', 'pattern'),
    [
        ('<div id="ks-app"></div>', 'never loads /__kaleidoscope__/static/kaleidoscope.js'),
        (
            '<script\tsrc="/__kaleidoscope__/static/kaleidoscope.js"></script>',
            "has no '<script ' for the CSP nonce",
        ),
        (
            '<script src="/__kaleidoscope__/static/kaleidoscope.js"></script>',
            'for the launch token',
        ),
    ],
)
def test_an_injector_refuses_a_shell_its_guards_cannot_rely_on(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shell: str,
    pattern: str,
) -> None:
    (tmp_path / 'shell.html').write_text(shell, encoding='utf-8')
    monkeypatch.setattr(injector, 'TEMPLATE_DIR', tmp_path)

    with pytest.raises(RuntimeError, match=pattern):
        ResponseInjector()
