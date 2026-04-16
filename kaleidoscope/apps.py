from django.apps import AppConfig


class KaleidoscopeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'kaleidoscope'
    verbose_name = 'Kaleidoscope'

    def ready(self) -> None:
        import kaleidoscope.checks  # noqa: PLC0415, F401
