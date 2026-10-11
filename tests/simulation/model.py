from __future__ import annotations

from dataclasses import dataclass, field

from tests.toolbar import PANEL_IDS_DEFAULT, PANEL_IDS_ISOLATED


@dataclass(frozen=True)
class CapturedExpectation:
    is_ajax: bool
    method: str
    path: str
    query_count: int
    status_code: int


@dataclass(frozen=True)
class PageExpectation:
    method: str
    path: str
    status_code: int
    view: str


def _panels_enabled_default() -> dict[str, bool]:
    return {panel_id: panel_id not in PANEL_IDS_ISOLATED for panel_id in PANEL_IDS_DEFAULT}


@dataclass
class ToolbarModel:
    cache_calls_max: int
    requests_stored_max: int
    cache_calls: list[tuple[str, bool]] | None = field(default_factory=list)
    cache_present: set[str] = field(default_factory=set)
    page_request: PageExpectation | None = None
    page_timer: PageExpectation | None = None
    panels_enabled: dict[str, bool] = field(default_factory=_panels_enabled_default)
    static_used: list[str] | None = None
    store: list[CapturedExpectation] = field(default_factory=list)
    store_known: bool = True
    templates_count: int | None = None
    templates_seen: bool = False
    track_ajax: bool = True
    track_page: bool = True

    def active(self, panel_id: str) -> bool:
        if not self.panels_enabled[panel_id]:
            return False

        if panel_id in PANEL_IDS_ISOLATED:
            return True

        return not self.isolated()

    def cache_calls_push(self, calls: list[tuple[str, bool]] | None, *, is_ajax: bool) -> None:
        if calls is None:
            self.cache_calls = None

            return

        if not is_ajax:
            self.cache_calls = list(calls)

            return

        if self.cache_calls is None:
            return

        self.cache_calls.extend(calls)
        del self.cache_calls[:-self.cache_calls_max]

    def enabled_set(self, panel_id: str, *, enabled: bool) -> None:
        if enabled:
            if panel_id in PANEL_IDS_ISOLATED:
                for isolated in PANEL_IDS_ISOLATED:
                    self.panels_enabled[isolated] = False

        self.panels_enabled[panel_id] = enabled

    def isolated(self) -> bool:
        return any(self.panels_enabled[panel_id] for panel_id in PANEL_IDS_ISOLATED)

    def store_push(self, expectation: CapturedExpectation | None, *, is_ajax: bool) -> None:
        if expectation is None:
            self.store_known = False

            if not is_ajax:
                self.store.clear()

            return

        if not is_ajax:
            self.store.clear()
            self.store_known = True

        self.store.append(expectation)
        del self.store[:-self.requests_stored_max]

    def tracking(self, *, is_ajax: bool) -> bool:
        if is_ajax:
            return self.track_ajax

        return self.track_page
