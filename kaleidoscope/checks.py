import inspect

from django.conf import settings
from django.core import checks
from django.middleware.gzip import GZipMiddleware
from django.utils.module_loading import import_string

from kaleidoscope.middleware import KaleidoscopeMiddleware
from kaleidoscope.panel import Panel
from kaleidoscope.registry import DEFAULT_PANELS, PANELS_MAX


MIDDLEWARE_MAX = 256
SETTING_SEQUENCE_TYPES = (list, tuple)


def _is_middleware_class(middleware_class: type, middleware_path: str) -> bool:
    if not inspect.isclass(middleware_class):
        message = f'middleware_class must be a class: {middleware_class!r}'
        raise TypeError(message)

    try:
        cls = import_string(middleware_path)
    except ImportError:
        return False

    return _is_subclass(cls, middleware_class)


def _is_subclass(value: object, base: type) -> bool:
    if not inspect.isclass(base):
        message = f'base must be a class: {base!r}'
        raise TypeError(message)

    if not inspect.isclass(value):
        return False

    return issubclass(value, base)


def check_middleware(
    app_configs: object,
    **_kwargs: object,
) -> list[checks.Warning]:
    _ = app_configs

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
        warning = checks.Warning(
            'kaleidoscope.middleware.KaleidoscopeMiddleware is missing from MIDDLEWARE.',
            hint='Add kaleidoscope.middleware.KaleidoscopeMiddleware to MIDDLEWARE.',
            id='kaleidoscope.W001',
        )

        errors.append(warning)

        return errors

    if len(kaleidoscope_indexes) != 1:
        warning = checks.Warning(
            'kaleidoscope.middleware.KaleidoscopeMiddleware occurs multiple times in MIDDLEWARE.',
            hint='Load kaleidoscope.middleware.KaleidoscopeMiddleware only once in MIDDLEWARE.',
            id='kaleidoscope.W002',
        )

        errors.append(warning)

        return errors

    if gzip_index is None:
        return errors

    if kaleidoscope_indexes[0] < gzip_index:
        warning = checks.Warning(
            'kaleidoscope.middleware.KaleidoscopeMiddleware occurs before '
            'django.middleware.gzip.GZipMiddleware in MIDDLEWARE.',
            hint=(
                'Move kaleidoscope.middleware.KaleidoscopeMiddleware to after '
                'django.middleware.gzip.GZipMiddleware in MIDDLEWARE.'
            ),
            id='kaleidoscope.W003',
        )

        errors.append(warning)

    return errors


def check_ignore_paths(
    app_configs: object,
    **_kwargs: object,
) -> list[checks.Warning]:
    _ = app_configs

    errors = []
    ignore_paths = getattr(settings, 'KALEIDOSCOPE_IGNORE_PATHS', [])

    if isinstance(ignore_paths, SETTING_SEQUENCE_TYPES):
        if all(isinstance(path, str) for path in ignore_paths):
            return errors

    warning = checks.Warning(
        'KALEIDOSCOPE_IGNORE_PATHS must be a list or tuple of path prefixes.',
        hint='Set KALEIDOSCOPE_IGNORE_PATHS to a list such as ["/admin/", "/media/"].',
        id='kaleidoscope.W007',
    )

    errors.append(warning)

    return errors


def check_internal_ips(
    app_configs: object,
    **_kwargs: object,
) -> list[checks.Warning]:
    _ = app_configs

    errors = []
    callback = getattr(settings, 'KALEIDOSCOPE_SHOW_CALLBACK', None)

    if callback is not None:
        return errors

    if not getattr(settings, 'INTERNAL_IPS', None):
        warning = checks.Warning(
            'INTERNAL_IPS is empty or not set. '
            'The kaleidoscope will not be visible unless KALEIDOSCOPE_SHOW_CALLBACK is configured.',
            hint='Set INTERNAL_IPS (e.g. ["127.0.0.1"]) or define KALEIDOSCOPE_SHOW_CALLBACK.',
            id='kaleidoscope.W004',
        )

        errors.append(warning)

    return errors


def check_panels(
    app_configs: object,
    **_kwargs: object,
) -> list[checks.Warning]:
    _ = app_configs

    errors = []
    panel_paths = getattr(settings, 'KALEIDOSCOPE_PANELS', DEFAULT_PANELS)

    if not isinstance(panel_paths, SETTING_SEQUENCE_TYPES):
        warning = checks.Warning(
            'KALEIDOSCOPE_PANELS must be a list or tuple of dotted paths to Panel classes.',
            hint='Set KALEIDOSCOPE_PANELS to a list of dotted paths, like the default panels.',
            id='kaleidoscope.W008',
        )

        errors.append(warning)

        return errors

    for path in panel_paths[:PANELS_MAX]:
        try:
            cls = import_string(path)
        except ImportError:
            warning = checks.Warning(
                f'Panel class {path!r} could not be imported.',
                hint='Verify the dotted path is correct and the module is installed.',
                id='kaleidoscope.W005',
            )

            errors.append(warning)

            continue

        if not _is_subclass(cls, Panel):
            warning = checks.Warning(
                f'{path!r} is not a subclass of kaleidoscope.panel.Panel.',
                hint='Each entry in KALEIDOSCOPE_PANELS must be a Panel subclass.',
                id='kaleidoscope.W006',
            )

            errors.append(warning)

    return errors
