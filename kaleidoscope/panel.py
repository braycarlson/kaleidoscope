from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from kaleidoscope.context import KaleidoscopeContext


@dataclass(frozen=True, slots=True)
class ServerTimingMetric:
    key: str
    description: str
    duration: float

    def __post_init__(self) -> None:
        if not isinstance(self.key, str):
            message = f'a metric key must be text: {self.key!r}'
            raise TypeError(message)

        if not self.key:
            message = 'a metric key must not be empty'
            raise ValueError(message)

        if not isinstance(self.description, str):
            message = f'a metric description must be text: {self.description!r}'
            raise TypeError(message)

        if isinstance(self.duration, bool):
            message = f'a metric duration must be a number, not a bool: {self.duration!r}'
            raise TypeError(message)

        if not isinstance(self.duration, (int, float)):
            message = f'a metric duration must be a number: {self.duration!r}'
            raise TypeError(message)


class Panel(ABC):
    panel_id: str = ''
    title: str = ''
    default_enabled: bool = True
    follows_view: bool = False
    isolate: bool = False

    def __init__(self) -> None:
        name = type(self).__name__

        if not isinstance(self.panel_id, str):
            message = f'{name}.panel_id must be text: {self.panel_id!r}'
            raise TypeError(message)

        if not isinstance(self.title, str):
            message = f'{name}.title must be text: {self.title!r}'
            raise TypeError(message)

        if not isinstance(self.default_enabled, bool):
            message = f'{name}.default_enabled must be a bool: {self.default_enabled!r}'
            raise TypeError(message)

        if not isinstance(self.follows_view, bool):
            message = f'{name}.follows_view must be a bool: {self.follows_view!r}'
            raise TypeError(message)

        if not isinstance(self.isolate, bool):
            message = f'{name}.isolate must be a bool: {self.isolate!r}'
            raise TypeError(message)

        self.enabled = self.default_enabled

    @abstractmethod
    def get_data(self) -> dict:
        ...

    @abstractmethod
    def get_summary(self) -> str:
        ...

    def get_server_timing(self, context: KaleidoscopeContext) -> list[ServerTimingMetric]:
        _ = context

        return []

    def handle_action(self, action: str, request: HttpRequest) -> HttpResponse | None:
        _ = action
        _ = request

        return None


class Installable(ABC):
    @abstractmethod
    def install(self) -> None:
        ...

    @abstractmethod
    def uninstall(self) -> None:
        ...


class RequestHook(ABC):
    @abstractmethod
    def process_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        ...


class ResponseHook(ABC):
    @abstractmethod
    def process_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        ...
