from __future__ import annotations

from django.apps import AppConfig


class BookstoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bookstore'
    verbose_name = 'Bookstore'

    def ready(self) -> None:
        from bookstore import receivers

        _ = receivers
