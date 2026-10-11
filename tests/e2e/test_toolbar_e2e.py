from __future__ import annotations

import pytest

from typing import TYPE_CHECKING

from kaleidoscope.panels.timer import TimerPanel
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX

from tests.toolbar import PANEL_IDS_DEFAULT, PANEL_IDS_ISOLATED

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext

    from tests.e2e.conftest import ToolbarPage
    from tests.testapp.models import Author


expect = pytest.importorskip('playwright.sync_api').expect
pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures('transactional_db')]
PANEL_IDS_RECORDING = tuple(panel for panel in PANEL_IDS_DEFAULT if panel not in PANEL_IDS_ISOLATED)
PREFERENCES_SIDE = "JSON.parse(localStorage.getItem('kaleidoscope_preferences')).side"
TAB_DRAG_PX = 150


def test_the_toolbar_mounts_inside_an_open_shadow_root(toolbar: ToolbarPage) -> None:
    toolbar.open('/plain/')

    host_shadow = toolbar.page.evaluate("document.getElementById('ks-app').shadowRoot !== null")

    assert host_shadow is True
    expect(toolbar.page.locator('body > p')).to_have_text('plain')


def test_the_collapsed_toolbar_leaves_the_page_clickable(toolbar: ToolbarPage) -> None:
    toolbar.open('/ajax/')
    toolbar.page.locator('#fetch').click()

    expect(toolbar.page.locator('#result')).to_contain_text('fetch')


def test_the_strip_lists_every_panel(toolbar: ToolbarPage) -> None:
    toolbar.open('/plain/')
    toolbar.strip_open()

    expect(toolbar.page.locator('[data-ks-panel]')).to_have_count(len(PANEL_IDS_DEFAULT))


def test_the_queries_panel_counts_the_n_plus_one_page(
    toolbar: ToolbarPage,
    library_live: list[Author],
) -> None:
    toolbar.open('/page/')
    toolbar.strip_open()
    toolbar.panel_open('queries')

    panel = toolbar.page.locator('[data-ks="panel"]')

    expect(toolbar.page.locator('[data-ks="panel-title"]')).to_have_text('SQL Queries')
    expect(panel).to_contain_text('/page/')
    expect(panel).to_contain_text(str(1 + len(library_live)))


@pytest.mark.parametrize('button', ['fetch', 'xhr'])
def test_ajax_requests_appear_in_the_queries_panel(toolbar: ToolbarPage, button: str) -> None:
    toolbar.open('/ajax/')
    toolbar.strip_open()
    toolbar.panel_open('queries')

    panel = toolbar.page.locator('[data-ks="panel"]')
    cells_ajax = panel.get_by_role('cell', name='AJAX', exact=True)
    cells_page = panel.get_by_role('cell', name='PAGE', exact=True)

    expect(cells_page).to_have_count(1)
    expect(cells_ajax).to_have_count(0)

    toolbar.page.evaluate(f"document.getElementById('{button}').click()")

    expect(toolbar.page.locator('#result')).to_contain_text(button)
    expect(cells_ajax).to_have_count(1)


@pytest.mark.parametrize('panel_id', PANEL_IDS_RECORDING)
def test_every_panel_opens_with_its_data(
    toolbar: ToolbarPage,
    library_live: list[Author],
    panel_id: str,
) -> None:
    _ = library_live

    toolbar.open('/work/?queries=3&templates=2&cache=set:alpha,get:alpha')
    toolbar.strip_open()
    toolbar.panel_open(panel_id)

    panel = toolbar.page.locator('[data-ks="panel"]')

    expect(panel).not_to_contain_text('Loading...')
    expect(toolbar.page.locator('[data-ks-panel-error]')).to_have_count(0)


def test_the_templates_panel_drills_into_a_queryset(
    toolbar: ToolbarPage,
    library_live: list[Author],
) -> None:
    toolbar.open('/page/')
    toolbar.strip_open()
    toolbar.panel_open('templates')

    panel = toolbar.page.locator('[data-ks="panel"]')

    panel.locator('tbody tr', has_text='testapp/page.html').first.click()
    panel.get_by_role('button', name='authors', exact=True).click()

    expect(panel).to_contain_text('QuerySet [Author]')
    expect(panel).to_contain_text(f'<Author pk={library_live[0].pk}>')


def test_a_statement_names_its_template_line_and_explains_its_plan(
    toolbar: ToolbarPage,
    library_live: list[Author],
) -> None:
    _ = library_live

    toolbar.open('/page/')
    toolbar.strip_open()
    toolbar.panel_open('queries')

    panel = toolbar.page.locator('[data-ks="panel"]')

    panel.locator('tbody tr', has_text='/page/').first.click()

    template_lines = panel.locator('[data-ks="query-template"]')
    template_line = template_lines.filter(has_text='{{ author.books.count }}').first

    expect(template_lines.filter(has_text='{% for author in authors %}')).to_have_count(1)
    expect(template_line).to_have_text('testapp/page.html:12 {{ author.books.count }}')

    template_line.click()
    panel.locator('[data-ks="explain"]').click()

    expect(panel).to_contain_text('EXPLAIN QUERY PLAN')
    expect(panel).to_contain_text('testapp_book')


def test_a_disabled_panel_stays_disabled_after_a_reload(toolbar: ToolbarPage) -> None:
    toolbar.open('/plain/')
    toolbar.strip_open()

    toggle = toolbar.page.locator('[data-ks-toggle="cache"]')

    expect(toggle).to_have_attribute('aria-checked', 'true')

    toggle.click()

    expect(toggle).to_have_attribute('aria-checked', 'false')

    toolbar.page.reload()
    toolbar.page.locator('[data-ks="strip"]').wait_for()

    expect(toggle).to_have_attribute('aria-checked', 'false')


def test_a_foreign_page_cannot_toggle_a_panel(toolbar: ToolbarPage) -> None:
    toolbar.console_expected.append('status of 403')

    url = f'{toolbar.base_url}{KALEIDOSCOPE_URL_PREFIX}panels/profiling/enable/'

    toolbar.page.set_content(f'<img src="{url}" alt="">', wait_until='load')
    toolbar.open('/plain/')
    toolbar.strip_open()

    toggle = toolbar.page.locator('[data-ks-toggle="profiling"]')

    expect(toggle).to_have_attribute('aria-checked', 'false')


def test_the_toolbar_works_from_the_keyboard(toolbar: ToolbarPage) -> None:
    toolbar.open('/plain/')
    toolbar.page.locator('[data-ks="tab"]').focus()
    toolbar.page.keyboard.press('Enter')

    expect(toolbar.page.locator('[data-ks="strip"]')).to_be_visible()

    toggle = toolbar.page.locator('[data-ks-toggle="signals"]')

    toggle.focus()
    toolbar.page.keyboard.press('Space')

    expect(toggle).to_have_attribute('aria-checked', 'false')


def test_the_side_and_theme_survive_a_reload(toolbar: ToolbarPage) -> None:
    toolbar.open('/plain/')
    toolbar.strip_open()
    toolbar.page.locator('[data-ks="swap"]').click()
    toolbar.page.locator('[data-ks="theme"]').click()

    assert toolbar.page.evaluate(PREFERENCES_SIDE) == 'left'
    assert toolbar.page.evaluate("localStorage.getItem('ks-theme')") == 'light'

    toolbar.page.reload()
    toolbar.page.locator('[data-ks="strip"]').wait_for()

    assert toolbar.page.evaluate(PREFERENCES_SIDE) == 'left'

    expect(toolbar.page.locator('[data-ks="theme"]')).to_have_attribute(
        'aria-label',
        'Use the dark theme',
    )


def test_a_panel_whose_data_fails_says_so(
    toolbar: ToolbarPage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(self: TimerPanel) -> dict:
        _ = self
        message = 'the timer is broken'

        raise RuntimeError(message)

    monkeypatch.setattr(TimerPanel, 'get_data', broken)
    toolbar.console_expected.append('status of 500')

    toolbar.open('/plain/')
    toolbar.strip_open()
    toolbar.page.locator('[data-ks-panel="timer"]').click()

    expect(toolbar.page.locator('[data-ks-panel-error]')).to_contain_text('HTTP 500')


def test_the_profiling_panel_shows_a_profile_once_enabled(
    toolbar: ToolbarPage,
    library_live: list[Author],
) -> None:
    _ = library_live

    toolbar.open('/plain/')
    toolbar.strip_open()
    toolbar.page.locator('[data-ks-toggle="profiling"]').click()

    expect(toolbar.page.locator('[data-ks="strip"]')).to_contain_text('Isolation Mode')

    toolbar.page.goto(toolbar.base_url + '/work/?queries=20&templates=3')
    toolbar.page.locator('[data-ks="strip"]').wait_for()
    toolbar.panel_open('profiling')

    expect(toolbar.page.locator('[data-ks="panel"]')).to_contain_text('Open in New Tab')


def test_the_mobile_layout_moves_between_strip_and_panel(toolbar: ToolbarPage) -> None:
    toolbar.page.set_viewport_size({'height': 800, 'width': 400})
    toolbar.open('/plain/')
    toolbar.strip_open()
    toolbar.panel_open('timer')

    expect(toolbar.page.locator('[data-ks="strip"]')).to_have_count(0)

    toolbar.page.locator('[data-ks="panel-back"]').click()

    expect(toolbar.page.locator('[data-ks="strip"]')).to_be_visible()


def test_the_copy_button_copies_the_panel_data(
    toolbar: ToolbarPage,
    context: BrowserContext,
) -> None:
    context.grant_permissions(['clipboard-read', 'clipboard-write'])
    toolbar.open('/plain/')
    toolbar.strip_open()
    toolbar.panel_open('timer')
    toolbar.page.locator('[data-ks="panel"] button[title="Copy to clipboard"]').first.click()

    copied = toolbar.page.evaluate('navigator.clipboard.readText()')

    assert 'method' in copied
    assert '/plain/' in copied


def test_the_tab_remembers_where_it_was_dragged(toolbar: ToolbarPage) -> None:
    toolbar.open('/plain/')

    box = toolbar.page.locator('[data-ks="tab"]').bounding_box()

    assert box is not None

    grip_x = box['x'] + 10
    grip_y = box['y'] + 10

    toolbar.page.mouse.move(grip_x, grip_y)
    toolbar.page.mouse.down()
    toolbar.page.mouse.move(grip_x, grip_y - TAB_DRAG_PX, steps=5)
    toolbar.page.mouse.up()

    stored = float(toolbar.page.evaluate("localStorage.getItem('kaleidoscope_tab_top')"))

    assert stored == pytest.approx(box['y'] - TAB_DRAG_PX, abs=1)
    expect(toolbar.page.locator('[data-ks="strip"]')).to_have_count(0)

    toolbar.page.reload()

    box_after = toolbar.page.locator('[data-ks="tab"]').bounding_box()

    assert box_after is not None
    assert box_after['y'] == pytest.approx(stored, abs=1)
