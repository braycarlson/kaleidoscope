from __future__ import annotations

import itertools
import logging
import platform

import django

from importlib.metadata import distributions
from typing import TYPE_CHECKING

from kaleidoscope.panel import Panel

if TYPE_CHECKING:
    from importlib.metadata import PackageMetadata


DESCRIPTION_LENGTH_MAX = 120
PACKAGES_MAX = 4_096
_SUMMARY_MISSING = frozenset({'', 'UNKNOWN'})

logger = logging.getLogger(__name__)


def _description_of(metadata: PackageMetadata) -> str:
    summary = _metadata_text(metadata, 'Summary')

    if summary not in _SUMMARY_MISSING:
        return summary

    description = _metadata_text(metadata, 'Description')

    if description in _SUMMARY_MISSING:
        return ''

    line_first = description.strip().split('\n', maxsplit=1)[0].strip()

    if len(line_first) > DESCRIPTION_LENGTH_MAX:
        return line_first[:DESCRIPTION_LENGTH_MAX - 3] + '...'

    return line_first


def _metadata_of(distribution: object) -> PackageMetadata | None:
    try:
        metadata = distribution.metadata  # ty:ignore[unresolved-attribute]
    except Exception:
        logger.exception('Kaleidoscope could not read the metadata of %r', distribution)
        metadata = None

    return metadata


def _metadata_text(metadata: PackageMetadata, key: str) -> str:
    if not isinstance(key, str):
        message = f'a metadata key must be text: {key!r}'
        raise TypeError(message)

    if key not in metadata:
        return ''

    value = metadata[key]

    if isinstance(value, str):
        return value

    return ''


def _name_lowered(entry: tuple[str, PackageMetadata]) -> str:
    return entry[0].lower()


def _packages() -> list[dict]:
    entries = []

    for distribution in itertools.islice(distributions(), PACKAGES_MAX):
        metadata = _metadata_of(distribution)

        if metadata is None:
            continue

        name = _metadata_text(metadata, 'Name').strip()

        if not name:
            continue

        entry = (name, metadata)

        entries.append(entry)

    entries.sort(key=_name_lowered)

    packages = []
    seen = set()

    for name, metadata in entries:
        lowered = name.lower()

        if lowered in seen:
            continue

        seen.add(lowered)

        package = {
            'description': _description_of(metadata),
            'name': name,
            'version': _metadata_text(metadata, 'Version'),
        }

        packages.append(package)

    return packages


class VersionsPanel(Panel):
    panel_id = 'versions'
    title = 'Versions'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict | None = None

    def get_data(self) -> dict:
        data = self._data

        if data is not None:
            return data

        packages = _packages()

        data = {
            'count': len(packages),
            'django': django.get_version(),
            'packages': packages,
            'python': platform.python_version(),
        }

        self._data = data

        return data

    def get_summary(self) -> str:
        return f'{self.get_data()["count"]} packages'
