from __future__ import annotations

import json
import warnings

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.views.debug import SafeExceptionReporterFilter

from kaleidoscope.panel import Panel


MASKED_VALUE = '********'
SETTINGS_KEYS_MAX = 4_096
_MISSING = object()


class _SettingsFilter(SafeExceptionReporterFilter):
    cleansed_substitute = MASKED_VALUE


def _repr_safe(value: object) -> str:
    try:
        text = repr(value)
    except Exception:
        text = f'<{type(value).__name__}>'

    return text


def _setting_keys() -> list[str]:
    return [key for key in sorted(dir(settings))[:SETTINGS_KEYS_MAX] if key.isupper()]


def _setting_read(key: str) -> object:
    if not isinstance(key, str):
        message = f'a setting name must be text: {key!r}'
        raise TypeError(message)

    if not key.isupper():
        message = f'a setting name must be upper case: {key!r}'
        raise ValueError(message)

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=DeprecationWarning)
        warnings.simplefilter('ignore', category=PendingDeprecationWarning)

        try:
            value = getattr(settings, key)
        except (AttributeError, ImproperlyConfigured):
            value = _MISSING

    return value


def _setting_serialized(key: str, value: object) -> object:
    if not isinstance(key, str):
        message = f'a setting name must be text: {key!r}'
        raise TypeError(message)

    try:
        cleansed = _SettingsFilter().cleanse_setting(key, value)
    except RecursionError:
        return MASKED_VALUE

    try:
        json.dumps(cleansed, allow_nan=False)
    except (OverflowError, RecursionError, TypeError, ValueError):
        return _repr_safe(cleansed)

    return cleansed


class SettingsPanel(Panel):
    panel_id = 'settings'
    title = 'Settings'

    def __init__(self) -> None:
        super().__init__()

        self._count: int | None = None

    def get_data(self) -> dict:
        items = {}

        for key in _setting_keys():
            value = _setting_read(key)

            if value is _MISSING:
                continue

            items[key] = _setting_serialized(key, value)

        self._count = len(items)

        return {'count': len(items), 'settings': items}

    def get_summary(self) -> str:
        count = self._count

        if count is None:
            count = len(_setting_keys())

        return f'{count} settings'
