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


class Panel(ABC):
    panel_id: str = ''
    title: str = ''
    default_enabled: bool = True
    isolate: bool = False

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

        if getattr(cls, '__abstractmethods__', None):
            return

    def __init__(self) -> None:
        self._enabled = self.default_enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @abstractmethod
    def get_data(self) -> dict:
        ...

    @abstractmethod
    def get_summary(self) -> str:
        ...

    def get_metadata(self) -> dict:
        return {
            'id': self.panel_id,
            'isolate': self.isolate,
            'summary': self.get_summary(),
            'title': self.title,
        }

    def get_server_timing(self) -> list[ServerTimingMetric]:
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


class AsyncRequestHook(ABC):
    @abstractmethod
    async def aprocess_request(self, request: HttpRequest, context: KaleidoscopeContext) -> None:
        ...


class AsyncResponseHook(ABC):
    @abstractmethod
    async def aprocess_response(
        self,
        request: HttpRequest,
        response: HttpResponse,
        context: KaleidoscopeContext,
    ) -> None:
        ...
