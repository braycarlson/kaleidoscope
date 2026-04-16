from __future__ import annotations

import platform
import threading

import django

from importlib.metadata import distributions

from kaleidoscope.constants import DESCRIPTION_MAX_LENGTH, PACKAGES_MAX
from kaleidoscope.panel import Panel


class VersionsPanel(Panel):
    panel_id = 'versions'
    title = 'Versions'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict | None = None
        self._lock = threading.Lock()

    def _extract_description(self, dist: object) -> str:
        summary = getattr(dist, 'metadata', {}).get('Summary', '') or ''

        if summary and summary != 'UNKNOWN':
            return summary

        description = getattr(dist, 'metadata', {}).get('Description', '') or ''

        if not description or description == 'UNKNOWN':
            return ''

        first_line = description.strip().split('\n', maxsplit=1)[0].strip()

        if len(first_line) > DESCRIPTION_MAX_LENGTH:
            return first_line[:DESCRIPTION_MAX_LENGTH - 3] + '...'

        return first_line

    def _get_packages(self) -> list[dict]:
        packages = []
        seen = set()

        sorted_dists = sorted(
            distributions(),
            key=lambda dist: dist.metadata['Name'].lower(),
        )

        for dist in sorted_dists[:PACKAGES_MAX]:
            name = dist.metadata['Name']
            lower = name.lower()

            if lower in seen:
                continue

            seen.add(lower)

            packages.append({
                'description': self._extract_description(dist),
                'name': name,
                'version': dist.metadata['Version'],
            })

        return packages

    def get_data(self) -> dict:
        with self._lock:
            if self._data:
                return self._data

        packages = self._get_packages()

        data = {
            'count': len(packages),
            'django': django.get_version(),
            'packages': packages,
            'python': platform.python_version(),
        }

        with self._lock:
            self._data = data

        return data

    def get_summary(self) -> str:
        with self._lock:
            if self._data:
                return f'{self._data["count"]} packages'

        count = len({
            dist.metadata['Name'].lower()
            for dist in list(distributions())[:PACKAGES_MAX]
        })

        return f'{count} packages'
