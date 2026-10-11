from __future__ import annotations

import encodings
import json
import math
import pkgutil

from encodings.aliases import aliases

from hypothesis import strategies as st


CHARACTER_NULL = chr(0)
CHARACTER_OVERRIDE_RIGHT_TO_LEFT = chr(0x202E)
TEXT_LENGTH_MAX = 60

CHARSETS_NOTABLE = (
    '',
    'utf-8',
    'UTF-8',
    'iso-8859-1',
    'latin-1',
    'ascii',
    'utf-16',
    'cp1252',
    'shift_jis',
    'undefined',
    'no-such-charset',
)

CODEC_MODULES = frozenset(module.name for module in pkgutil.iter_modules(encodings.__path__))
CODECS = tuple(sorted(CODEC_MODULES | set(aliases.values())))
CHARSETS = st.one_of(st.sampled_from(CHARSETS_NOTABLE), st.sampled_from(CODECS))

CONTENT_TYPES = (
    'text/html',
    'TEXT/HTML',
    'application/xhtml+xml',
    'application/json',
    'text/plain',
    'application/octet-stream',
    'text/html ',
    '',
)

HTML_FRAGMENTS = (
    '<html>',
    '</html>',
    '<head>',
    '</head>',
    '<body>',
    '</body>',
    '</BODY>',
    '</Body >',
    '</body\n>',
    '<body class="x">',
    '<script>',
    '</script>',
    '<!-- </body> -->',
    '/__kaleidoscope__/static/kaleidoscope.js',
    '<p>',
    'é',
    '☃',
    '\U0001f600',
    CHARACTER_NULL,
    CHARACTER_OVERRIDE_RIGHT_TO_LEFT,
)

PATH_TEXTS_HOSTILE = (
    '',
    '/',
    '//',
    '..',
    '../',
    '%2e%2e/',
    '%00',
    'panels',
    'panels/',
    'panels//data/',
    'panels/queries',
    'panels/queries/data',
    'panels/queries/action/',
    'panels/queries/action/clear',
    'panels/templates/action/value/',
    'static',
    'static/',
    'static/kaleidoscope.js',
    'static/../router.py',
    'static/%2e%2e/router.py',
    'static/kaleidoscope.js/..',
)

SQL_KEYWORDS = (
    'SELECT',
    'FROM',
    'WHERE',
    'AND',
    'OR',
    'IN',
    'JOIN',
    'ON',
    'ORDER BY',
    'LIMIT',
    'INSERT INTO',
    'VALUES',
    'UPDATE',
    'SET',
    'DELETE',
    ';',
    '(',
    ')',
    ',',
    '=',
    '*',
    '%s',
    '"book"',
    'book.id',
    '--',
    '/*',
    '*/',
)

VALUES_NOTABLE = (
    '',
    ' ',
    CHARACTER_NULL,
    'true',
    'null',
    "' OR 1=1 --",
    '<script>alert(1)</script>',
    '../../etc/passwd',
    f'{CHARACTER_OVERRIDE_RIGHT_TO_LEFT}A',
    'A' * 300,
)

TEXT_CHARACTERS = st.characters(exclude_categories=('Cs',))
TEXTS_ANY = st.text(max_size=TEXT_LENGTH_MAX)

TEXTS_HOSTILE = st.one_of(
    st.sampled_from(VALUES_NOTABLE),
    st.text(alphabet=TEXT_CHARACTERS, max_size=TEXT_LENGTH_MAX),
)

FLOATS_ANY = st.floats(allow_nan=True, allow_infinity=True)

SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    FLOATS_ANY,
    TEXTS_HOSTILE,
    st.binary(max_size=20),
)

VALUES_NESTED = st.recursive(
    SCALARS,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.tuples(children, children),
        st.dictionaries(TEXTS_HOSTILE, children, max_size=4),
        st.frozensets(st.integers(), max_size=4),
    ),
    max_leaves=12,
)

HTML_DOCUMENTS = st.lists(
    st.one_of(st.sampled_from(HTML_FRAGMENTS), st.text(alphabet=TEXT_CHARACTERS, max_size=12)),
    max_size=25,
).map(''.join)

SQL_STATEMENTS = st.lists(
    st.one_of(
        st.sampled_from(SQL_KEYWORDS),
        st.integers(min_value=-(10**12), max_value=10**12).map(str),
        st.floats(allow_nan=False, allow_infinity=False).map(repr),
        TEXTS_HOSTILE.map(lambda text: "'" + text.replace("'", "''") + "'"),
        st.text(alphabet=TEXT_CHARACTERS, max_size=10),
        st.sampled_from((' ', '  ', '\n', '\t', ' \r\n ')),
    ),
    max_size=40,
).map(' '.join)

TOOLBAR_PATH_SEGMENTS = (*PATH_TEXTS_HOSTILE, 'queries', 'data', 'action', 'x')

TOOLBAR_PATHS = st.one_of(
    st.sampled_from(PATH_TEXTS_HOSTILE),
    st.text(alphabet=TEXT_CHARACTERS, max_size=TEXT_LENGTH_MAX),
    st.lists(st.sampled_from(TOOLBAR_PATH_SEGMENTS), max_size=6).map('/'.join),
)


def json_strict_load(text: str | bytes) -> object:
    def constant_refused(name: str) -> float:
        message = f'JSON carries the non-standard constant {name}'
        raise ValueError(message)

    return json.loads(text, parse_constant=constant_refused)


def json_strict_valid(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)

    return True
