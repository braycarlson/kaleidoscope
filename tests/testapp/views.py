from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.http import HttpResponse
from django.shortcuts import render

from tests.testapp import work
from tests.testapp.models import Author
from tests.testapp.work import (
    SPIN_MS,
    WorkFailedError,
    WorkPlan,
    cache_operation_run,
    fragments_render,
    queries_run,
    query_lingering,
    query_run,
    response_build,
    spin_for_profile,
)

if TYPE_CHECKING:
    from uuid import UUID

    from django.http import HttpRequest

    from tests.testapp.converters import Color


PAGE_DOCUMENT = (
    '<!DOCTYPE html><html><head><title>Plain</title></head>'
    '<body><p>plain</p></body></html>'
)


def ajax_view(request: HttpRequest) -> HttpResponse:
    return render(request, 'testapp/ajax.html')


async def async_view(request: HttpRequest) -> HttpResponse:
    _ = request
    count = await Author.objects.acount()
    document = PAGE_DOCUMENT.replace('plain', f'authors {count}')

    return HttpResponse(document)


def body_view(request: HttpRequest) -> HttpResponse:
    length = len(request.body)

    return HttpResponse(str(length), content_type='text/plain')


def color_view(request: HttpRequest, color: Color) -> HttpResponse:
    _ = request
    document = PAGE_DOCUMENT.replace('plain', color.name)

    return HttpResponse(document)


def ignored_view(request: HttpRequest) -> HttpResponse:
    _ = request

    return HttpResponse(PAGE_DOCUMENT)


def page_view(request: HttpRequest) -> HttpResponse:
    authors = Author.objects.all()
    context = {'authors': authors, 'title': 'Library'}

    return render(request, 'testapp/page.html', context)


def plain_view(request: HttpRequest) -> HttpResponse:
    _ = request

    return HttpResponse(PAGE_DOCUMENT)


async def spin_async_view(request: HttpRequest) -> HttpResponse:
    _ = request

    spin_for_profile(SPIN_MS)
    await asyncio.sleep(0)

    return HttpResponse(PAGE_DOCUMENT)


def spin_view(request: HttpRequest) -> HttpResponse:
    _ = request

    spin_for_profile(SPIN_MS)

    return HttpResponse(PAGE_DOCUMENT)


def uuid_view(request: HttpRequest, identifier: UUID) -> HttpResponse:
    _ = request
    document = PAGE_DOCUMENT.replace('plain', str(identifier))

    return HttpResponse(document)


async def work_async_view(request: HttpRequest) -> HttpResponse:
    plan = WorkPlan.parse(request.GET)

    for index in range(plan.queries):
        await sync_to_async(query_run)(plan, index)
        await asyncio.sleep(0)

    for operation in plan.cache_operations:
        await sync_to_async(cache_operation_run)(operation)
        await asyncio.sleep(0)

    if plan.linger:
        task = asyncio.ensure_future(query_lingering(plan))

        work.lingering.append(task)

    if plan.fail:
        message = f'work {plan.token} failed on purpose'
        raise WorkFailedError(message)

    return response_build(plan, '', 0)


def work_view(request: HttpRequest) -> HttpResponse:
    plan = WorkPlan.parse(request.GET)
    body_length = len(request.body) if plan.read_body else 0

    queries_run(plan)

    for operation in plan.cache_operations:
        cache_operation_run(operation)

    fragments = fragments_render(plan)

    if plan.fail:
        message = f'work {plan.token} failed on purpose'
        raise WorkFailedError(message)

    return response_build(plan, fragments, body_length)
