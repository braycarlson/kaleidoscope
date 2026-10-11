from django.apps import AppConfig
from django.core import checks

from kaleidoscope.checks import (
    check_ignore_paths,
    check_internal_ips,
    check_middleware,
    check_panels,
)
from kaleidoscope.injector import launch_token


class KaleidoscopeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'kaleidoscope'
    verbose_name = 'Kaleidoscope'

    def ready(self) -> None:
        launch_token()

        checks.register(check_ignore_paths)
        checks.register(check_internal_ips)
        checks.register(check_middleware)
        checks.register(check_panels)
