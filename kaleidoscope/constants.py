from enum import StrEnum


KALEIDOSCOPE_URL_PREFIX = '/__kaleidoscope__/'

PANELS_MAX = 64
MIDDLEWARE_MAX = 256
QUERIES_PER_REQUEST_MAX = 10_000
REQUESTS_STORED_MAX = 200
SIGNALS_MAX = 128
RECEIVERS_PER_SIGNAL_MAX = 512
PACKAGES_MAX = 4_096
SETTINGS_KEYS_MAX = 4_096
FINDERS_MAX = 64
STATIC_FILES_MAX = 100_000
TEMPLATES_PER_REQUEST_MAX = 2_048
CACHE_CALLS_MAX = 50_000
CACHES_MAX = 256
MEMORY_DIFF_ROWS_MAX = 50
URL_PARTS_MAX = 16
CONTEXT_KEYS_MAX = 1_024
CONTEXT_DICTS_MAX = 256
CONTENT_SEARCH_ITERATIONS_MAX = 1_000_000
STACK_FRAMES_MAX = 256
WRAPPED_DEPTH_MAX = 32
FORMAT_ARGS_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 120
INJECTABLE_CONTENT_MAX = 10_485_760

LINE_PROFILER_FUNCTIONS_MAX = 32
LINE_PROFILER_TIMINGS_MAX = 10_000


class Header:
    REQUEST_ID = 'X-Kaleidoscope-Request-Id'
    SERVER_TIMING = 'Server-Timing'


class RouteSegment(StrEnum):
    PANELS = 'panels/'
    STATIC = 'static/'


class PanelEndpoint(StrEnum):
    DATA = 'data'
    ENABLE = 'enable'
    DISABLE = 'disable'
    ACTION = 'action'


class ProfilingAction(StrEnum):
    HTML = 'html'


class QueryAction(StrEnum):
    CLEAR = 'clear'
    TRACK_AJAX_ON = 'track-ajax-on'
    TRACK_AJAX_OFF = 'track-ajax-off'
    TRACK_PAGE_ON = 'track-page-on'
    TRACK_PAGE_OFF = 'track-page-off'


class StateKey(StrEnum):
    LINE_PROFILER = 'line_profiler'
    MEMORY_BEFORE = 'memory_before'
    PROFILER = 'profiler'
    QUERY_CAPTURE = 'query_capture'
    QUERY_START = 'query_start'
    REQUEST_DATA = 'request_data'
    TIMER_START = 'timer_start'
