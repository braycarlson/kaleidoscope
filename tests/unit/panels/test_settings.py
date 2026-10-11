from __future__ import annotations

import json
import warnings

import pytest

import django

from django.test import override_settings
from django.views.debug import SafeExceptionReporterFilter

from kaleidoscope.panels import settings as settings_panel
from kaleidoscope.panels.settings import (
    MASKED_VALUE,
    SettingsPanel,
    _setting_read,
    _setting_serialized,
)


CANARY = 'canary-secret-value'

CANARIES = (
    'canary-nested-password',
    'canary-nested-signature',
    'canary-nested-token',
    'canary-passwd-value',
    'canary-token-value',
    'kaleidoscope-tests-secret-key',
)

SECRET_NAMES_HIDDEN_BY_DJANGO = (
    'DATABASE_PASSWD',
    'GITHUB_TOKEN',
    'SIGNING_SECRET',
    'SSH_PASSPHRASE',
    'STRIPE_API_KEY',
    'WEBHOOK_SIGNATURE',
)


class _Unprintable:
    def __repr__(self) -> str:
        message = 'no repr for you'
        raise RuntimeError(message)


def test_settings_mask_secret_names_at_the_top_level() -> None:
    settings_shown = SettingsPanel().get_data()['settings']

    assert settings_shown['SECRET_KEY'] == MASKED_VALUE
    assert settings_shown['API_TOKEN'] == MASKED_VALUE


def test_settings_mask_secret_names_nested_inside_dictionaries_and_lists() -> None:
    credentials = SettingsPanel().get_data()['settings']['SERVICE_CREDENTIALS']

    assert credentials['primary'] == {'HOST': 'service.internal', 'PASSWORD': MASKED_VALUE}
    assert credentials['replicas'] == [{'HOST': 'replica.internal', 'TOKEN': MASKED_VALUE}]


def test_no_secret_value_appears_anywhere_in_the_settings_data() -> None:
    serialized = json.dumps(SettingsPanel().get_data())

    for canary in CANARIES:
        assert canary not in serialized


def test_settings_that_json_cannot_hold_are_shown_as_their_repr() -> None:
    settings_shown = SettingsPanel().get_data()['settings']

    assert settings_shown['BASE_DIR'].startswith(('PosixPath(', 'WindowsPath('))
    assert settings_shown['DEBUG'] is True


def test_reading_every_setting_emits_no_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        SettingsPanel().get_data()

    deprecations = [
        warning
        for warning in caught
        if issubclass(warning.category, DeprecationWarning | PendingDeprecationWarning)
    ]

    assert deprecations == []


@override_settings(
    MAILERS={'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}},
)
def test_settings_survive_settings_that_refuse_to_be_read() -> None:
    data = SettingsPanel().get_data()

    assert data['count'] == len(data['settings'])
    assert 'MAILERS' in data['settings']

    if django.VERSION >= (6, 1):
        assert 'EMAIL_HOST_USER' not in data['settings']


def test_settings_summary_counts_the_settings_shown() -> None:
    panel = SettingsPanel()
    summary_before = panel.get_summary()
    data = panel.get_data()

    assert panel.get_summary() == f'{data["count"]} settings'
    assert summary_before.endswith(' settings')


@pytest.mark.parametrize('name', SECRET_NAMES_HIDDEN_BY_DJANGO)
def test_settings_hide_every_name_the_django_error_page_hides(name: str) -> None:
    hidden_by_django = SafeExceptionReporterFilter().cleanse_setting(name, CANARY)
    overrides = {name: CANARY}

    with override_settings(**overrides):
        shown = SettingsPanel().get_data()['settings'][name]

    assert hidden_by_django != CANARY
    assert shown == MASKED_VALUE


def test_settings_show_a_value_that_neither_json_nor_repr_can_hold_by_its_type() -> None:
    assert _setting_serialized('CUSTOM', _Unprintable()) == '<_Unprintable>'


def test_settings_mask_a_value_too_deeply_nested_to_cleanse() -> None:
    looped: dict = {}
    looped['self'] = looped

    assert _setting_serialized('LOOPED', looped) == MASKED_VALUE


def test_settings_skip_a_name_that_cannot_be_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def setting_keys() -> list[str]:
        return ['DEBUG', 'NO_SUCH_SETTING_ANYWHERE']

    monkeypatch.setattr(settings_panel, '_setting_keys', setting_keys)

    assert SettingsPanel().get_data() == {'count': 1, 'settings': {'DEBUG': True}}


@pytest.mark.parametrize(
    ('name', 'error', 'pattern'),
    [
        (7, TypeError, 'a setting name must be text: 7'),
        ('debug', ValueError, "a setting name must be upper case: 'debug'"),
    ],
)
def test_settings_refuse_to_read_a_name_that_is_no_setting(
    name: object,
    error: type[Exception],
    pattern: str,
) -> None:
    with pytest.raises(error, match=pattern):
        _setting_read(name)  # ty:ignore[invalid-argument-type]


def test_settings_refuse_to_serialize_under_a_name_that_is_not_text() -> None:
    with pytest.raises(TypeError, match='a setting name must be text: 7'):
        _setting_serialized(7, 'value')  # ty:ignore[invalid-argument-type]
