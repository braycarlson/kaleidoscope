from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urlparse

import sqlparse

from kaleidoscope.constants import CONTENT_SEARCH_ITERATIONS_MAX


class SqlNormalizer:
    def normalize(self, sql: str) -> str:
        parsed = sqlparse.parse(sql)

        if not parsed:
            return sql

        parts = []

        for token in parsed[0].flatten():
            if token.ttype in sqlparse.tokens.Literal.String.Single or token.ttype in (
                sqlparse.tokens.Literal.Number.Float,
                sqlparse.tokens.Literal.Number.Integer,
            ):
                parts.append('%s')
            elif token.ttype in sqlparse.tokens.Whitespace:
                parts.append(' ')
            else:
                parts.append(str(token))

        return ''.join(parts)


class PathShortener:
    def __init__(self, *, max_length: int = 20, tail_segments: int = 3) -> None:
        self._max_length = max_length
        self._tail_segments = tail_segments

    def shorten(self, path: str) -> str:
        normalized = path.replace('\\', '/')
        parts = PurePosixPath(normalized).parts

        if len(parts) <= self._tail_segments:
            return normalized

        short = '.../' + '/'.join(parts[-self._tail_segments:])

        if len(short) > self._max_length:
            return short[:self._max_length - 3] + '...'

        return short

    def shorten_url(self, url: str) -> str:
        path = urlparse(url).path

        if len(path) <= self._max_length:
            return path

        return path[:self._max_length - 3] + '...'


class StaticFileExtractor:
    def __init__(self, static_url: str) -> None:
        self._static_url = static_url

    def extract(self, content: str) -> list[str]:
        used: set[str] = set()
        search = self._static_url
        search_len = len(search)
        content_len = len(content)
        terminators = frozenset('"\'?#) \n\r>')

        start = 0

        for _ in range(CONTENT_SEARCH_ITERATIONS_MAX):
            index = content.find(search, start)

            if index == -1:
                break

            path_start = index + search_len
            path_end = path_start

            while path_end < content_len and content[path_end] not in terminators:
                path_end += 1

            path = content[path_start:path_end]

            if path:
                used.add(path)

            start = path_start

        return sorted(used)
