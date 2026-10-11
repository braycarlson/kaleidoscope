from __future__ import annotations

from django.urls import path, register_converter

from tests.testapp import views
from tests.testapp.converters import ColorConverter


register_converter(ColorConverter, 'color')

urlpatterns = (
    path('ajax/', views.ajax_view, name='ajax'),
    path('async/', views.async_view, name='async'),
    path('body/', views.body_view, name='body'),
    path('color/<color:color>/', views.color_view, name='color'),
    path('ignored/', views.ignored_view, name='ignored'),
    path('page/', views.page_view, name='page'),
    path('plain/', views.plain_view, name='plain'),
    path('spin/', views.spin_view, name='spin'),
    path('spin-async/', views.spin_async_view, name='spin-async'),
    path('uuid/<uuid:identifier>/', views.uuid_view, name='uuid'),
    path('work/', views.work_view, name='work'),
    path('work-async/', views.work_async_view, name='work-async'),
)
