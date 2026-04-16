from __future__ import annotations

import threading

from typing import TYPE_CHECKING

from kaleidoscope.normalizer import StaticFileExtractor
from kaleidoscope.panel import Panel, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext

try:
    from django.contrib.staticfiles.finders import get_finders
    HAS_STATICFILES = True
except ImportError:
    HAS_STATICFILES = False


class StaticFilesPanel(Panel, ResponseHook):
    panel_id = 'staticfiles'
    title = 'Static Files'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict = {}
        self._extractor: StaticFileExtractor | None = None
        self._files_cache = None
        self._lock = threading.Lock()

    def _collect_static_files(self) -> list[dict]:
        if self._files_cache is not None:
            return self._files_cache

        if not HAS_STATICFILES:
            return []

        files = []

        for finder in get_finders():
            for (path, storage) in finder.list([]):
                location = ''

                if hasattr(storage, 'location'):
                    location = str(storage.location)

                if not location and hasattr(storage, 'base_location'):
                    location = str(storage.base_location)

                files.append({
                    'finder': finder.__class__.__name__,
                    'full_path': f'{location}/{path}' if location else path,
                    'path': path,
                })

        files.sort(key=lambda f: f['path'])
        self._files_cache = files

        return files

    def _get_extractor(self) -> StaticFileExtractor:
        if self._extractor is None:
            from django.conf import settings  # noqa: PLC0415

            static_url = getattr(settings, 'STATIC_URL', '/static/')
            self._extractor = StaticFileExtractor(static_url)

        return self._extractor

    def get_data(self) -> dict:
        with self._lock:
            return dict(self._data)

    def get_summary(self) -> str:
        with self._lock:
            used = self._data.get('used_count', 0)
            total = self._data.get('all_count', 0)

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

        if context.is_ajax:
            return

        if not hasattr(response, 'content'):
            return

        content = response.content.decode('utf-8', errors='ignore')
        extractor = self._get_extractor()
        used = extractor.extract(content)
        all_files = self._collect_static_files()

        with self._lock:
            self._data = {
                'all_count': len(all_files),
                'all_files': all_files,
                'used_count': len(used),
                'used_files': used,
            }
