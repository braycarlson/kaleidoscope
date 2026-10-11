from __future__ import annotations

import email.message
import platform

import django
import pytest

from kaleidoscope.panels import versions
from kaleidoscope.panels.versions import VersionsPanel, _metadata_text


class _Distribution:
    def __init__(self, fields: dict[str, str]) -> None:
        self.fields = fields

    @property
    def metadata(self) -> email.message.Message:
        message = email.message.Message()

        for key, value in self.fields.items():
            message[key] = value

        return message


class _DistributionLoose:
    def __init__(self, metadata: dict[str, object]) -> None:
        self.metadata = metadata


class _DistributionBroken:
    @property
    def metadata(self) -> email.message.Message:
        encoding = 'utf-8'
        message = 'the metadata file is unreadable'

        raise UnicodeDecodeError(encoding, b'\xff', 0, 1, message)


def _panel_with(monkeypatch: pytest.MonkeyPatch, entries: list[object]) -> VersionsPanel:
    def distributions() -> list[object]:
        return entries

    monkeypatch.setattr(versions, 'distributions', distributions)

    return VersionsPanel()


def test_versions_list_the_installed_packages_sorted_by_name() -> None:
    data = VersionsPanel().get_data()
    names = [package['name'] for package in data['packages']]

    assert names == sorted(names, key=str.lower)
    assert 'Django' in names
    assert data['count'] == len(names)
    assert data['django'] == django.get_version()
    assert data['python'] == platform.python_version()


def test_versions_skip_a_distribution_without_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        _Distribution({'Version': '1.0'}),
        _Distribution({'Name': '   ', 'Version': '2.0'}),
        _Distribution({'Name': 'alpha', 'Version': '3.0'}),
    ]

    packages = _panel_with(monkeypatch, entries).get_data()['packages']

    assert packages == [{'description': '', 'name': 'alpha', 'version': '3.0'}]


def test_versions_skip_a_distribution_whose_metadata_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    entries = [_DistributionBroken(), _Distribution({'Name': 'alpha', 'Version': '1.0'})]
    packages = _panel_with(monkeypatch, entries).get_data()['packages']

    assert [package['name'] for package in packages] == ['alpha']
    assert 'could not read the metadata' in caplog.text


def test_versions_keep_the_first_of_two_distributions_with_one_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = [
        _Distribution({'Name': 'Alpha', 'Version': '1.0'}),
        _Distribution({'Name': 'alpha', 'Version': '2.0'}),
    ]

    packages = _panel_with(monkeypatch, entries).get_data()['packages']

    assert len(packages) == 1


@pytest.mark.parametrize(
    ('fields', 'expected'),
    [
        ({'Summary': 'A summary.'}, 'A summary.'),
        ({'Summary': 'UNKNOWN', 'Description': 'First line\nsecond line'}, 'First line'),
        ({'Description': 'UNKNOWN'}, ''),
        ({}, ''),
        ({'Description': 'x' * 300}, 'x' * 117 + '...'),
    ],
)
def test_versions_describe_a_package_by_summary_then_description(
    monkeypatch: pytest.MonkeyPatch,
    fields: dict[str, str],
    expected: str,
) -> None:
    entry = _Distribution({'Name': 'alpha', 'Version': '1.0', **fields})
    packages = _panel_with(monkeypatch, [entry]).get_data()['packages']

    assert packages[0]['description'] == expected


def test_versions_summary_counts_the_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        _Distribution({'Name': 'alpha', 'Version': '1.0'}),
        _Distribution({'Name': 'beta', 'Version': '1.0'}),
    ]

    assert _panel_with(monkeypatch, entries).get_summary() == '2 packages'


def test_versions_scan_the_environment_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def distributions() -> list[object]:
        calls.append(1)

        return [_Distribution({'Name': 'alpha', 'Version': '1.0'})]

    monkeypatch.setattr(versions, 'distributions', distributions)

    panel = VersionsPanel()

    panel.get_summary()
    panel.get_data()
    panel.get_summary()

    assert len(calls) == 1


def test_versions_show_metadata_that_is_not_text_as_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = {'Name': 'alpha', 'Summary': ['not', 'text'], 'Version': 3}
    entries = [_DistributionLoose(metadata)]
    packages = _panel_with(monkeypatch, entries).get_data()['packages']

    assert packages == [{'description': '', 'name': 'alpha', 'version': ''}]


def test_versions_refuse_a_metadata_key_that_is_not_text() -> None:
    metadata = {'Name': 'alpha'}

    with pytest.raises(TypeError, match='a metadata key must be text: 7'):
        _metadata_text(metadata, 7)  # ty:ignore[invalid-argument-type]
