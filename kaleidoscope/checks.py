import inspect

from django.conf import settings
from django.core.checks import Warning, register  # noqa: A004
from django.middleware.gzip import GZipMiddleware
from django.utils.module_loading import import_string

from kaleidoscope.constants import MIDDLEWARE_MAX, PANELS_MAX
from kaleidoscope.middleware import KaleidoscopeMiddleware


def _is_middleware_class(middleware_class: type, middleware_path: str) -> bool:
    try:
        cls = import_string(middleware_path)
    except ImportError:
        return False

    return inspect.isclass(cls) and issubclass(cls, middleware_class)


@register
def check_middleware(
    _app_configs: object,
    **_kwargs: object,
) -> list[Warning]:
    errors = []
    gzip_index = None
    kaleidoscope_indexes = []

    middleware_list = settings.MIDDLEWARE

    for middleware_index, middleware in enumerate(middleware_list[:MIDDLEWARE_MAX]):
        if _is_middleware_class(GZipMiddleware, middleware):
            gzip_index = middleware_index
            continue

        if _is_middleware_class(KaleidoscopeMiddleware, middleware):
            kaleidoscope_indexes.append(middleware_index)

    if not kaleidoscope_indexes:
        errors.append(
            Warning(
                'kaleidoscope.middleware.KaleidoscopeMiddleware is missing from MIDDLEWARE.',
                hint='Add kaleidoscope.middleware.KaleidoscopeMiddleware to MIDDLEWARE.',
                id='kaleidoscope.W001',
            )
        )

        return errors

    if len(kaleidoscope_indexes) != 1:
        errors.append(
            Warning(
                'kaleidoscope.middleware.KaleidoscopeMiddleware occurs multiple times in MIDDLEWARE.',
                hint='Load kaleidoscope.middleware.KaleidoscopeMiddleware only once in MIDDLEWARE.',
                id='kaleidoscope.W002',
            )
        )

        return errors

    if gzip_index is not None and kaleidoscope_indexes[0] < gzip_index:
        errors.append(
            Warning(
                'kaleidoscope.middleware.KaleidoscopeMiddleware occurs before '
                'django.middleware.gzip.GZipMiddleware in MIDDLEWARE.',
                hint=(
                    'Move kaleidoscope.middleware.KaleidoscopeMiddleware to after '
                    'django.middleware.gzip.GZipMiddleware in MIDDLEWARE.'
                ),
                id='kaleidoscope.W003',
            )
        )

    return errors


@register
def check_internal_ips(
    _app_configs: object,
    **_kwargs: object,
) -> list[Warning]:
    errors = []

    callback = getattr(settings, 'KALEIDOSCOPE_SHOW_CALLBACK', None)

    if callback is None and not getattr(settings, 'INTERNAL_IPS', None):
        errors.append(
            Warning(
                'INTERNAL_IPS is empty or not set. '
                'The kaleidoscope will not be visible unless KALEIDOSCOPE_SHOW_CALLBACK is configured.',
                hint='Set INTERNAL_IPS (e.g. ["127.0.0.1"]) or define KALEIDOSCOPE_SHOW_CALLBACK.',
                id='kaleidoscope.W004',
            )
        )

    return errors


@register
def check_panels(
    _app_configs: object,
    **_kwargs: object,
) -> list[Warning]:
    from kaleidoscope.panel import Panel  # noqa: PLC0415
    from kaleidoscope.registry import DEFAULT_PANELS  # noqa: PLC0415

    errors = []
    panel_paths = getattr(settings, 'KALEIDOSCOPE_PANELS', DEFAULT_PANELS)

    for path in panel_paths[:PANELS_MAX]:
        try:
            cls = import_string(path)
        except ImportError:
            errors.append(
                Warning(
                    f'Panel class {path!r} could not be imported.',
                    hint='Verify the dotted path is correct and the module is installed.',
                    id='kaleidoscope.W005',
                )
            )

            continue

        if not (inspect.isclass(cls) and issubclass(cls, Panel)):
            errors.append(
                Warning(
                    f'{path!r} is not a subclass of kaleidoscope.panel.Panel.',
                    hint='Each entry in KALEIDOSCOPE_PANELS must be a Panel subclass.',
                    id='kaleidoscope.W006',
                )
            )

    return errors
