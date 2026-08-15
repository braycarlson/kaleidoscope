from __future__ import annotations

from django.contrib import admin

from bookstore.models import (
    Author,
    Book,
    Category,
    Customer,
    Order,
    OrderItem,
    Publisher,
    Review,
    Tag
)


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ['name', 'country', 'publisher']


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'publisher', 'price']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'country']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['reference', 'customer', 'status', 'placed_on']


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'book', 'quantity', 'unit_price']


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'country']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['book', 'reviewer_name', 'rating']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
