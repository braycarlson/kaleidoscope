from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING, Any

from kaleidoscope.panel import Panel, RequestHook, ResponseHook

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext


answers: dict[str, Any] = {}
thread_events: list[tuple[str, str, bool]] = []


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False

    return True


class AnsweringPanel(Panel):
    panel_id = 'answering'
    title = 'Answering'

    def get_data(self) -> Any:
        return answers.get('data')

    def get_server_timing(self, context: KaleidoscopeContext) -> Any:
        _ = context

        return answers.get('timing')

    def get_summary(self) -> Any:
        return answers.get('summary')

    def handle_action(self, action: str, request: HttpRequest) -> Any:
        _ = action
        _ = request

        return answers.get('action')


class ThreadRecordingPanel(Panel, RequestHook, ResponseHook):
    panel_id = 'thread_recording'
    title = 'Thread Recording'

    def get_data(self) -> dict:
        return {}

    def get_summary(self) -> str:
        return ''

    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        _ = request
        _ = context
        event = (self.panel_id, 'request', _loop_running())

        thread_events.append(event)

    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        _ = request
        _ = response
        _ = context
        event = (self.panel_id, 'response', _loop_running())

        thread_events.append(event)


class ThreadFollowingPanel(ThreadRecordingPanel):
    follows_view = True
    panel_id = 'thread_following'
    title = 'Thread Following'
