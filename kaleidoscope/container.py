from __future__ import annotations


class ServiceContainer:
    def __init__(self) -> None:
        self._services: dict[type, object] = {}

    def register(self, service_type: type, instance: object) -> None:
        assert isinstance(instance, service_type)

        self._services[service_type] = instance

    def get(self, service_type: type) -> object | None:
        return self._services.get(service_type)

    def has(self, service_type: type) -> bool:
        return service_type in self._services
