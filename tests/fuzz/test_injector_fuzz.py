from __future__ import annotations

import re

import pytest

from hypothesis import example, given
from hypothesis import strategies as st

from django.http import HttpResponse
from django.test import RequestFactory

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.injector import ResponseInjector, server_timing_entry

from tests.fuzz.settings import fuzz_settings
from tests.fuzz.strategies import CHARSETS, CONTENT_TYPES, FLOATS_ANY, HTML_DOCUMENTS, TEXTS_ANY
from tests.toolbar import shell_text


pytestmark = pytest.mark.fuzz
BODY_CLOSE = re.compile(r'</body\s*>', re.IGNORECASE)
HTML_TYPES = frozenset({'text/html', 'application/xhtml+xml'})
INJECTABLE_STATUSES = frozenset(range(200, 300)) - {204, 205, 206}

SERVER_TIMING_ENTRY = re.compile(
    r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+;dur=-?\d+\.\d{2};desc=\"(?:[^\"\\\x00-\x1f\x7f]|\\.)*\"",
)

STATUSES = (200, 201, 204, 206, 302, 404, 500)


def _declared_charset(charset: str) -> str:
    return charset or 'utf-8'


def _decoded(content: bytes, charset: str) -> str | None:
    try:
        return content.decode(_declared_charset(charset))
    except (LookupError, UnicodeError):
        return None


@fuzz_settings
@given(
    document=HTML_DOCUMENTS,
    content_type=st.sampled_from(CONTENT_TYPES),
    charset=CHARSETS,
    encode_as=st.sampled_from(['utf-8', 'iso-8859-1', 'utf-16']),
    status=st.sampled_from(STATUSES),
    is_ajax=st.booleans(),
    encoded=st.booleans(),
)
@example(
    document='<html><body>x</BODY></html>',
    content_type='text/html',
    charset='',
    encode_as='utf-8',
    status=200,
    is_ajax=False,
    encoded=False,
)
@example(
    document='<html><body>x</body></html>',
    content_type='text/html',
    charset='undefined',
    encode_as='utf-8',
    status=200,
    is_ajax=False,
    encoded=False,
)
def test_injector_only_ever_inserts_the_shell_before_the_last_closing_body(
    document: str,
    content_type: str,
    charset: str,
    encode_as: str,
    status: int,
    is_ajax: bool,
    encoded: bool,
) -> None:
    content = document.encode(encode_as, errors='replace')
    declared = f'{content_type}; charset={charset}' if charset else content_type
    response = HttpResponse(content, content_type=declared, status=status)

    if encoded:
        response['Content-Encoding'] = 'br'

    request = RequestFactory().get('/')
    context = KaleidoscopeContext(is_ajax=is_ajax)
    processed = ResponseInjector().process(request, response, context)
    after = processed.content

    if after == content:
        return

    before_text = _decoded(content, charset)
    after_text = _decoded(after, charset)
    media_type = content_type.partition(';')[0].strip().lower()

    assert not is_ajax
    assert not encoded
    assert status in INJECTABLE_STATUSES
    assert media_type in HTML_TYPES
    assert before_text is not None
    assert after_text is not None
    assert after_text.count(shell_text()) == before_text.count(shell_text()) + 1

    closings = list(BODY_CLOSE.finditer(after_text))
    index = closings[-1].start()

    assert after_text[index - len(shell_text()):index] == shell_text()
    assert after_text.replace(shell_text(), '', 1) == before_text
    assert int(processed['Content-Length']) == len(after)


@fuzz_settings
@given(name=TEXTS_ANY, duration=FLOATS_ANY, description=TEXTS_ANY)
@example(name='a\r\nb', duration=1.0, description='c\r\nd')
@example(name='x', duration=1e308, description='"\\')
def test_server_timing_entry_is_always_a_valid_header_value(
    name: str,
    duration: float,
    description: str,
) -> None:
    entry = server_timing_entry(name, duration, description)

    if entry is None:
        return

    assert SERVER_TIMING_ENTRY.fullmatch(entry)

    response = HttpResponse()
    response['Server-Timing'] = entry

    assert response['Server-Timing'] == entry
