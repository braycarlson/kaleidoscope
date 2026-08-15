from __future__ import annotations

from django.urls import path

from bookstore import views


app_name = 'bookstore'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('api/books/', views.api_book_list_view, name='api_book_list'),
    path('authors/', views.author_list_view, name='author_list'),
    path('books/', views.book_list_view, name='book_list'),
    path('books/optimized/', views.book_list_optimized_view, name='book_list_optimized'),
    path('books/<int:pk>/', views.book_detail_view, name='book_detail'),
    path('cache/', views.cache_view, name='cache'),
    path('customers/', views.customer_list_view, name='customer_list'),
    path('memory/', views.memory_view, name='memory'),
    path('orders/', views.order_list_view, name='order_list'),
    path('reports/', views.report_view, name='report'),
    path('search/', views.search_view, name='search')
]
