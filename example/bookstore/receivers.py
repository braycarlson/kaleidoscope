from __future__ import annotations

from typing_extensions import TYPE_CHECKING

from django.core.cache import cache
from django.core.signals import request_started
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from bookstore.models import Book, Order, OrderItem, Review

if TYPE_CHECKING:
    from django.db.models import Model


@receiver(pre_save, sender=Book)
def book_isbn_normalized(sender: type[Model], instance: Book, **kwargs: object) -> None:
    _ = sender
    _ = kwargs

    instance.isbn = instance.isbn.replace('-', '').upper()


@receiver(post_save, sender=Book)
def book_publisher_counted(sender: type[Model], instance: Book, **kwargs: object) -> None:
    _ = sender
    _ = kwargs

    cache.set(f'publisher-book-count-{instance.publisher_id}', instance.publisher.books.count(), 60)


@receiver(m2m_changed, sender=Book.categories.through)
def book_categories_denormalized(sender: type[Model], instance: Book, **kwargs: object) -> None:
    _ = sender
    _ = kwargs

    cache.set(f'book-categories-{instance.pk}', instance.category_names, 60)


@receiver(post_save, sender=Review)
def review_rating_recomputed(sender: type[Model], instance: Review, **kwargs: object) -> None:
    _ = sender
    _ = kwargs

    ratings = [review.rating for review in instance.book.reviews.all()]
    average = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    cache.set(f'book-rating-{instance.book_id}', average, 60)


@receiver(post_delete, sender=Review)
def review_rating_invalidated(sender: type[Model], instance: Review, **kwargs: object) -> None:
    _ = sender
    _ = kwargs

    cache.delete(f'book-rating-{instance.book_id}')


@receiver(post_save, sender=OrderItem)
def order_total_recomputed(sender: type[Model], instance: OrderItem, **kwargs: object) -> None:
    _ = sender
    _ = kwargs

    cache.set(f'order-total-{instance.order_id}', instance.order.total, 60)


@receiver(post_save, sender=Order)
def order_reference_cached(sender: type[Model], instance: Order, **kwargs: object) -> None:
    _ = sender
    _ = kwargs

    cache.set(f'order-reference-{instance.pk}', instance.reference, 60)


@receiver(request_started)
def feature_flags_loaded(sender: type, **kwargs: object) -> None:
    _ = sender
    _ = kwargs

    cache.get('feature-flags')
    cache.get('banner-message')
