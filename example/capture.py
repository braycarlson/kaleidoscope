from __future__ import annotations

import json
import socket
import subprocess
import sys
import time

from pathlib import Path
from typing_extensions import TYPE_CHECKING

from playwright.sync_api import sync_playwright

if TYPE_CHECKING:
    from playwright.sync_api import Page


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / 'database.sqlite3'
OUTPUT_DIR = BASE_DIR / 'screenshot'

HOST = '127.0.0.1'
PORT = 8765
BASE_URL = f'http://{HOST}:{PORT}'

ACTION_MS = 1200
DEVICE_SCALE_FACTOR = 2
POLL_SECONDS = 0.2
SERVER_TIMEOUT_SECONDS = 30
SETTLE_MS = 2000
SETTLE_PROFILE_MS = 7000

VIEWPORT = {'width': 1920, 'height': 1080}

ISOLATED_PANELS = ('line_profiling', 'memory', 'profiling')


def _ajax_fired(page: Page) -> None:
    page.evaluate('fetch("/api/books/", {headers: {"X-Requested-With": "XMLHttpRequest"}})')
    page.wait_for_timeout(2500)
    page.locator('tr', has_text='AJAX').first.click()


def _panel_disabled(page: Page, panel_id: str) -> None:
    page.request.get(f'{BASE_URL}/__kaleidoscope__/panels/{panel_id}/disable/')


def _panel_enabled(page: Page, panel_id: str) -> None:
    page.request.get(f'{BASE_URL}/__kaleidoscope__/panels/{panel_id}/enable/')


def _preferences_applied(page: Page, state: str, panel_id: str | None) -> None:
    preferences = {
        'active_panel': panel_id,
        'disabled': {},
        'order': [],
        'side': 'right',
        'state': state
    }

    payload = json.dumps(preferences)
    page.evaluate('value => localStorage.setItem("kaleidoscope_preferences", value)', payload)


def _request_expanded(page: Page) -> None:
    page.locator('tr', has_text='PAGE').first.click()


def _server_running() -> bool:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(POLL_SECONDS)

    code = connection.connect_ex((HOST, PORT))
    connection.close()

    return code == 0


def _server_started() -> subprocess.Popen:
    command = [
        sys.executable,
        str(BASE_DIR / 'manage.py'),
        'runserver',
        f'{HOST}:{PORT}',
        '--noreload'
    ]

    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + SERVER_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        if _server_running():
            return process

        time.sleep(POLL_SECONDS)

    process.terminate()

    message = f'the demo server did not come up on {BASE_URL}'
    raise RuntimeError(message)


def _shot_taken(page: Page, shot: dict) -> None:
    isolate = shot.get('isolate')

    if isolate is not None:
        _panel_enabled(page, isolate)

    page.goto(BASE_URL + shot['path'], wait_until='load')
    _preferences_applied(page, shot['state'], shot.get('panel'))

    page.goto(BASE_URL + shot['path'], wait_until='load')
    page.wait_for_timeout(shot.get('settle', SETTLE_MS))

    action = shot.get('action')

    if action is not None:
        action(page)
        page.wait_for_timeout(ACTION_MS)

    page.screenshot(path=str(OUTPUT_DIR / shot['name']))

    if isolate is not None:
        _panel_disabled(page, isolate)

    print(shot['name'])


def _shots_built() -> list[dict]:
    return [
        {'name': '01-dashboard.png', 'path': '/', 'state': 'collapsed'},
        {'name': '02-panel-strip.png', 'path': '/books/', 'state': 'strip'},
        {
            'action': _request_expanded,
            'name': '03-queries-n-plus-one.png',
            'panel': 'queries',
            'path': '/books/',
            'state': 'panel'
        },
        {
            'action': _similar_revealed,
            'name': '04-similar-queries.png',
            'panel': 'queries',
            'path': '/books/',
            'state': 'panel'
        },
        {
            'action': _request_expanded,
            'name': '05-queries-optimized.png',
            'panel': 'queries',
            'path': '/books/optimized/',
            'state': 'panel'
        },
        {
            'action': _request_expanded,
            'name': '06-queries-orders.png',
            'panel': 'queries',
            'path': '/orders/',
            'state': 'panel'
        },
        {
            'isolate': 'profiling',
            'name': '07-profiling.png',
            'panel': 'profiling',
            'path': '/reports/',
            'settle': SETTLE_PROFILE_MS,
            'state': 'panel'
        },
        {
            'isolate': 'line_profiling',
            'name': '08-line-profiler.png',
            'panel': 'line_profiling',
            'path': '/reports/',
            'state': 'panel'
        },
        {
            'isolate': 'memory',
            'name': '09-memory.png',
            'panel': 'memory',
            'path': '/memory/',
            'state': 'panel'
        },
        {'name': '10-templates.png', 'panel': 'templates', 'path': '/books/', 'state': 'panel'},
        {'name': '11-cache.png', 'panel': 'cache', 'path': '/cache/', 'state': 'panel'},
        {'name': '12-signals.png', 'panel': 'signals', 'path': '/orders/', 'state': 'panel'},
        {'name': '13-static-files.png', 'panel': 'staticfiles', 'path': '/', 'state': 'panel'},
        {'name': '14-settings.png', 'panel': 'settings', 'path': '/', 'state': 'panel'},
        {
            'name': '15-request.png',
            'panel': 'request',
            'path': '/search/?q=lantern',
            'state': 'panel'
        },
        {'name': '16-timer.png', 'panel': 'timer', 'path': '/books/', 'state': 'panel'},
        {'name': '17-versions.png', 'panel': 'versions', 'path': '/', 'state': 'panel'},
        {
            'action': _ajax_fired,
            'name': '18-queries-ajax.png',
            'panel': 'queries',
            'path': '/',
            'state': 'panel'
        }
    ]


def _shots_captured(shots: list[dict]) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE_FACTOR)
        page = context.new_page()

        page.goto(BASE_URL + '/', wait_until='load')

        for panel_id in ISOLATED_PANELS:
            _panel_disabled(page, panel_id)

        for shot in shots:
            _shot_taken(page, shot)

        context.close()
        browser.close()


def _similar_revealed(page: Page) -> None:
    _request_expanded(page)
    page.locator('div.cursor-pointer.select-none').first.click()


def main() -> int:
    if not DATABASE_PATH.is_file():
        print('no database found, run: just reset')
        return 1

    patterns = sys.argv[1:]
    shots = [
        shot for shot in _shots_built()
        if not patterns or any(pattern in shot['name'] for pattern in patterns)
    ]

    if not shots:
        print(f'no screenshot matched {patterns}')
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    process = None if _server_running() else _server_started()

    try:
        _shots_captured(shots)
    finally:
        if process is not None:
            process.terminate()
            process.wait()

    return 0


if __name__ == '__main__':
    sys.exit(main())
