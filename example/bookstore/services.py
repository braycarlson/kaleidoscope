from __future__ import annotations

from typing_extensions import TYPE_CHECKING

from django.core.cache import cache
from django.db.models import Avg, Count, Sum

from bookstore.models import Author, Book, Customer, Order, Publisher, Review

if TYPE_CHECKING:
    from django.db.models import QuerySet


BOOK_ROW_LIMIT = 60
CACHE_KEY_COUNT = 40
CUSTOMER_ROW_LIMIT = 25
MEMORY_RETAINED_ROWS = 4_000
MEMORY_ROW_COUNT = 40_000
ORDER_ROW_LIMIT = 25
SEARCH_ROW_LIMIT = 30

_rows_retained: list[dict] = []


def author_rows_python_side() -> list[dict]:
    authors = list(Author.objects.all())
    rows = []

    for author in authors:
        books = list(author.books.all())
        ratings = []

        for book in books:
            for review in book.reviews.all():
                ratings.append(review.rating)

        row = {
            'author': author,
            'average_rating': round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
            'book_count': author.books.count(),
            'publisher_name': author.publisher.name,
            'review_count': len(ratings)
        }

        rows.append(row)

    rows.sort(key=lambda row: row['average_rating'], reverse=True)

    return rows[:CUSTOMER_ROW_LIMIT]


def book_rows_optimized() -> QuerySet[Book]:
    return (
        Book.objects
        .select_related('author', 'author__publisher', 'publisher')
        .prefetch_related('categories', 'tags')
        .annotate(rating_average=Avg('reviews__rating'), tally=Count('reviews', distinct=True))
        .order_by('title')[:BOOK_ROW_LIMIT]
    )


def book_rows_unoptimized() -> list[Book]:
    return list(Book.objects.all()[:BOOK_ROW_LIMIT])


def cache_thrash_run() -> dict:
    hits = 0
    misses = 0

    for index in range(CACHE_KEY_COUNT):
        key = f'demo-cache-key-{index}'
        value = cache.get(key)

        if value is None:
            payload = {'index': index, 'payload': 'x' * 256}
            cache.set(key, payload, 5)
            misses += 1
        else:
            hits += 1

    warm_keys = [f'demo-cache-key-{index}' for index in range(10)]
    cache.get_many(warm_keys)

    for index in range(10):
        cache.has_key(f'demo-cache-key-{index}')
        cache.delete(f'demo-cache-key-{index}')

    cache.get_or_set('demo-catalog-size', Book.objects.count, 5)

    return {'hits': hits, 'keys': CACHE_KEY_COUNT, 'misses': misses}


def catalog_totals_optimized() -> dict:
    aggregate = Book.objects.aggregate(
        catalog_value=Sum('price'),
        rating_average=Avg('reviews__rating'),
        tally=Count('id', distinct=True)
    )

    return {
        'catalog_value': round(float(aggregate['catalog_value'] or 0), 2),
        'rating_average': round(float(aggregate['rating_average'] or 0), 2),
        'tally': aggregate['tally']
    }


def catalog_totals_python_side() -> dict:
    books = list(Book.objects.all())
    catalog_value = 0.0
    ratings = []

    for book in books:
        catalog_value += float(book.price)

        for review in book.reviews.all():
            ratings.append(review.rating)

    return {
        'catalog_value': round(catalog_value, 2),
        'rating_average': round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
        'tally': len(books)
    }


def customer_rows_python_side() -> list[dict]:
    customers = list(Customer.objects.all())
    rows = []

    for customer in customers:
        spend = 0.0
        units = 0

        for order in customer.orders.all():
            for item in order.items.all():
                spend += float(item.unit_price) * item.quantity
                units += item.quantity

        row = {
            'customer': customer,
            'order_count': customer.orders.count(),
            'spend': round(spend, 2),
            'units': units
        }

        rows.append(row)

    rows.sort(key=lambda row: row['spend'], reverse=True)

    return rows[:CUSTOMER_ROW_LIMIT]


def memory_churn_run() -> dict:
    rows = []

    for index in range(MEMORY_ROW_COUNT):
        row = {
            'digest': f'{index:08d}' * 4,
            'index': index,
            'label': f'row-{index}',
            'weights': [index * factor for factor in range(6)]
        }

        rows.append(row)

    index_by_label = {row['label']: row for row in rows}
    digests = [row['digest'] for row in rows]

    _rows_retained.extend(rows[:MEMORY_RETAINED_ROWS])

    return {
        'distinct_digests': len(set(digests)),
        'indexed': len(index_by_label),
        'retained': len(_rows_retained),
        'rows': len(rows)
    }


def order_rows_unoptimized() -> list[Order]:
    return list(Order.objects.all()[:ORDER_ROW_LIMIT])


def publisher_rows_unoptimized() -> list[Publisher]:
    return list(Publisher.objects.all())


def review_rows_unoptimized() -> list[Review]:
    return list(Review.objects.all()[:ORDER_ROW_LIMIT])


def search_results_python_side(term: str) -> list[dict]:
    books = list(Book.objects.filter(title__icontains=term))
    books.extend(Book.objects.filter(summary__icontains=term))
    books.extend(Book.objects.filter(author__name__icontains=term))

    seen = set()
    rows = []

    for book in books:
        if book.pk in seen:
            continue

        seen.add(book.pk)

        row = {
            'author_name': book.author.name,
            'book': book,
            'publisher_name': book.publisher.name,
            'rating': book.average_rating,
            'review_count': book.reviews.count()
        }

        rows.append(row)

    rows.sort(key=lambda row: row['rating'], reverse=True)

    return rows[:SEARCH_ROW_LIMIT]
