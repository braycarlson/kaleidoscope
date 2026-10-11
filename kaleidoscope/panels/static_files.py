from __future__ import annotations

import itertools
import logging

from typing import TYPE_CHECKING

from django.apps import apps
from django.conf import settings
from django.contrib.staticfiles.finders import get_finder
from django.http import HttpResponse, HttpResponseBase

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.injector import is_html_response
from kaleidoscope.panel import Panel, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpRequest


CONTENT_SEARCH_ITERATIONS_MAX = 1_000_000
FINDERS_MAX = 64
IGNORE_PATTERNS_DEFAULT = ('CVS', '.*', '*~')
STATIC_FILES_MAX = 100_000
_PATH_TERMINATORS = frozenset('"\'?#) \n\r>')

logger = logging.getLogger(__name__)


def _html_text(response: HttpResponse) -> str:
    if not isinstance(response, HttpResponse):
        message = f'the page text comes from an HttpResponse, not {type(response).__name__}'
        raise TypeError(message)

    try:
        text = response.content.decode(response.charset, errors='replace')
    except (LookupError, UnicodeError):
        text = response.content.decode('utf-8', errors='replace')

    return text


def _ignore_patterns() -> list[str]:
    config = apps.get_app_config('staticfiles')

    return list(getattr(config, 'ignore_patterns', IGNORE_PATTERNS_DEFAULT))


def _path_of(entry: dict) -> str:
    return entry['path']


def _static_files_listed() -> list[dict]:
    if not apps.is_installed('django.contrib.staticfiles'):
        return []

    files: list[dict] = []
    ignore_patterns = _ignore_patterns()

    for finder_path in list(settings.STATICFILES_FINDERS)[:FINDERS_MAX]:
        remaining = STATIC_FILES_MAX - len(files)

        if remaining <= 0:
            break

        try:
            finder = get_finder(finder_path)
            entries = list(itertools.islice(finder.list(ignore_patterns), remaining))
        except Exception:
            logger.exception('Kaleidoscope could not list the static files of %s', finder_path)
            continue

        for path, storage in entries:
            location = _storage_location(storage)

            file = {
                'finder': type(finder).__name__,
                'full_path': f'{location}/{path}' if location else path,
                'path': path,
            }

            files.append(file)

    files.sort(key=_path_of)

    return files


def _static_paths_used(content: str, static_url: str) -> list[str]:
    if not isinstance(content, str):
        message = f'content must be text, not {type(content).__name__}'
        raise TypeError(message)

    if not isinstance(static_url, str):
        message = f'static_url must be text: {static_url!r}'
        raise TypeError(message)

    if not static_url:
        return []

    used: set[str] = set()
    start = 0

    for _ in range(CONTENT_SEARCH_ITERATIONS_MAX):
        index = content.find(static_url, start)

        if index == -1:
            break

        path_start = index + len(static_url)
        path_end = path_start

        while path_end < len(content):
            if content[path_end] in _PATH_TERMINATORS:
                break

            path_end += 1

        path = content[path_start:path_end]

        if path:
            used.add(path)

        start = path_end

    return sorted(used)


def _storage_location(storage: object) -> str:
    location = getattr(storage, 'location', '') or getattr(storage, 'base_location', '')

    return str(location or '')


class StaticFilesPanel(Panel, ResponseHook):
    panel_id = 'staticfiles'
    title = 'Static Files'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}
        self._files: list[dict] | None = None

    def _files_listed(self) -> list[dict]:
        files = self._files

        if files is None:
            files = _static_files_listed()
            self._files = files

        return files

    def get_data(self) -> dict:
        return dict(self._data)

    def get_summary(self) -> str:
        data = self._data
        used = data.get('used_count', 0)
        total = data.get('all_count', 0)

        if used:
            return f'{used} used, {total} available'

        return f'{total} available'

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        _ = request

        if not isinstance(response, HttpResponseBase):
            message = f'{self.title} needs an HttpResponse, not {type(response).__name__}'
            raise TypeError(message)

        if not isinstance(context, KaleidoscopeContext):
            message = f'{self.title} needs a KaleidoscopeContext, not {type(context).__name__}'
            raise TypeError(message)

        if context.is_ajax:
            return

        if not is_html_response(response):
            return

        static_url = getattr(settings, 'STATIC_URL', None)
        used = _static_paths_used(_html_text(response), str(static_url) if static_url else '')
        files = self._files_listed()

        self._data = {
            'all_count': len(files),
            'all_files': files,
            'used_count': len(used),
            'used_files': used,
        }
