<picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/braycarlson/kaleidoscope/main/assets/logo-plain-ink.png">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/braycarlson/kaleidoscope/main/assets/logo-plain-white.png">
    <img alt="django-kaleidoscope" src="https://raw.githubusercontent.com/braycarlson/kaleidoscope/main/assets/logo-plain-white.png" width="600">
</picture>

&nbsp;

A debug toolbar for Django.

![SQL Queries panel](https://raw.githubusercontent.com/braycarlson/kaleidoscope/main/example/screenshot/03-queries-n-plus-one.png)

## Overview

The kaleidoscope toolbar records what a request did and renders it as a set of panels over the page. There are twelve panels by default, covering SQL, templates, cache calls, signals, static files, settings, versions, timing, memory, the request itself, and two profilers. This is useful for finding N+1 queries, slow views, and template rendering costs during development.

The toolbar installs as a single middleware and mounts into a shadow root, so the page it inspects cannot restyle it and its own stylesheet cannot reach the page.

## Prerequisites

- Django 4.2+
- Python 3.11+
- `DEBUG` must be `True`, unless `KALEIDOSCOPE_SHOW_CALLBACK` is set

## Installation

```
pip install django-kaleidoscope
```

Add the app, the middleware, and your address to your Django settings:

```python
INSTALLED_APPS = [
    'kaleidoscope'
]

MIDDLEWARE = [
    'kaleidoscope.middleware.KaleidoscopeMiddleware'
]

INTERNAL_IPS = ['127.0.0.1']
```

The middleware belongs after `GZipMiddleware`. A compressed response carries a `Content-Encoding` and the injector refuses it, so a toolbar loaded first never appears. A system check reports the ordering at startup.

## Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| `INTERNAL_IPS` | The addresses that see the toolbar while `DEBUG` is on. | `[]` |
| `KALEIDOSCOPE_IGNORE_PATHS` | The path prefixes the middleware skips. | `[]` |
| `KALEIDOSCOPE_PANELS` | The dotted paths of the panels to load. The load order is the strip's default order. | The twelve defaults |
| `KALEIDOSCOPE_SHOW_CALLBACK` | A dotted path to a callable taking the request, replacing the `DEBUG` and `INTERNAL_IPS` check. It may be sync or async, and is adapted to whichever the request needs. | `None` |
| `X_FRAME_OPTIONS` | The value must be `'SAMEORIGIN'` for the profiling panel. The Django default of `'DENY'` blocks the panel's iframe and it renders blank. | `'DENY'` |

There are six system checks at startup, reporting a missing middleware, a middleware registered twice, a middleware ordered before `GZipMiddleware`, an empty `INTERNAL_IPS` with no callback, a panel path that will not import, and a panel that is not a `Panel` subclass.

## Panels

| Panel | Description | Isolated |
|-------|-------------|----------|
| Timer | The wall time for the request, with its method, path, status, and whether it ran under ASGI. | |
| Versions | The versions of the installed packages. | |
| Request | The method, path, headers, cookies, GET and POST data, and the resolver match. | |
| SQL Queries | Each statement with its time, parameters, and stack, grouped into duplicates and N+1 candidates. | |
| Templates | Each `Template.render` call with its duration and serialized context variables. | |
| Cache | Each `add`, `clear`, `delete`, `delete_many`, `get`, `get_many`, `get_or_set`, `has_key`, `incr`, `set`, and `set_many` call with its key, result, and time. | |
| Static Files | The files referenced by the response, against each file the finders can see. | |
| Signals | The built-in Django signals and the receivers connected to each one. | |
| Settings | The resolved settings for the project. | |
| Memory | The heap difference across the request by type, split into allocated, freed, and unchanged. | Yes |
| Profiling | A pyinstrument call stack, rendered inline and openable in its own tab. | Yes |
| Line Profiler | The per-line hits, time, and share of total for the resolved view. | Yes |

The panels are toggled at runtime from the strip, which persists the panel order, side, active panel, and collapsed state in `localStorage`.

## How It Works

Each statement passes through a `connection.execute_wrapper` that records the SQL, its parameters, its duration in nanoseconds, and the stack that issued it with `site-packages` and kaleidoscope's own frames removed. A repeated statement is counted as a duplicate. The statements that differ only in their literals are normalized with sqlparse and grouped, which collapses a sixty-row page into one row reading `×460`.

A page request clears the store and opens a group, and each XHR that follows lands in that same group, so a page and the requests it fires are read together instead of one at a time. The page and AJAX tracking toggle separately.

The memory, profiling, and line profiler panels declare `isolate`. An enabled isolated panel suspends the others for that request: a pyinstrument sample is worth little while the SQL panel is walking a stack trace on each execute, so the measurement runs alone. The line profiler resolves the view through the URL resolver, unwraps decorator chains up to 32 deep, and adds the matching method and `dispatch` for class-based views.

The response injector accepts only `text/html` and `application/xhtml+xml` responses with a 2xx status, no `Content-Encoding`, and a body under 10 MB, splicing the shell before the final `</body>`. A streaming response is left alone. The CSP nonce comes from `django.middleware.csp.get_nonce` on Django 6 and is copied onto the injected script, falling back to `request._csp_nonce` and `request.csp_nonce` on older versions.

Each collector is bounded at 10,000 queries per request, 200 requests retained, 2,048 template renders, 50,000 cache calls, and 256 stack frames, so a runaway view degrades the panel rather than the process.

Each enabled panel also writes to the `Server-Timing` header, which puts panel totals in the network tab without opening the toolbar. The response carries `X-Kaleidoscope-Request-Id` for matching a request to its captured data.

## Example Project

The `example/` directory holds a Django project written to be slow. The columns carry no `db_index`, the model properties open a query each time they are read, and the aggregates are folded in Python instead of the database. Each page names the mistakes it is making.

| Page | Queries | Total |
|------|---------|-------|
| `/books/` | 882 | 277 ms |
| `/search/` | 1603 | 444 ms |
| `/authors/` | 673 | 194 ms |
| `/reports/` | 602 | 169 ms |
| `/customers/` | 503 | 143 ms |
| `/orders/` | 327 | 287 ms |
| `/` | 96 | 38 ms |
| `/books/optimized/` | 4 | 33 ms |

The `/books/optimized/` page renders the same sixty rows as `/books/` using `select_related`, `prefetch_related`, and `Count` and `Avg` annotations, which is the difference between 882 queries and 4.

```
just install
just reset
just run-server
```

The `just screenshot` recipe captures each panel into `example/screenshot/` and accepts a filter, such as `just screenshot queries`.
