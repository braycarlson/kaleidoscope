from __future__ import annotations

import json
import threading

from kaleidoscope.constants import SETTINGS_KEYS_MAX
from kaleidoscope.panel import Panel


MASKED_KEYWORDS = (
    'API_KEY',
    'KEY',
    'PASSWORD',
    'SECRET',
    'TOKEN',
)


class SettingsPanel(Panel):
    panel_id = 'settings'
    title = 'Settings'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict | None = None
        self._lock = threading.Lock()

    def _serialize(self, key: str, value: object) -> object:
        if any(keyword in key.upper() for keyword in MASKED_KEYWORDS):
            return '********'

        try:
            json.dumps(value)
        except (TypeError, ValueError):
            return repr(value)
        else:
            return value

    def get_data(self) -> dict:
        from django.conf import settings  # noqa: PLC0415

        items = {}

        all_keys = sorted(dir(settings))[:SETTINGS_KEYS_MAX]

        for key in all_keys:
            if key.isupper():
                value = getattr(settings, key)
                items[key] = self._serialize(key, value)

        data = {
            'count': len(items),
            'settings': items,
        }

        with self._lock:
            self._data = data

        return data

    def get_summary(self) -> str:
        with self._lock:
            if self._data:
                return f'{self._data["count"]} settings'

        from django.conf import settings  # noqa: PLC0415

        count = sum(
            1 for key in sorted(dir(settings))[:SETTINGS_KEYS_MAX]
            if key.isupper()
        )

        return f'{count} settings'
