from __future__ import annotations

import time

from typing_extensions import TYPE_CHECKING

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from bookstore.models import Author, Book, Category, Customer, Order, Publisher, Review, Tag
from bookstore.services import (
    author_rows_python_side,
    book_rows_optimized,
    book_rows_unoptimized,
    cache_thrash_run,
    catalog_totals_optimized,
    catalog_totals_python_side,
    customer_rows_python_side,
    memory_churn_run,
    order_rows_unoptimized,
    publisher_rows_unoptimized,
    review_rows_unoptimized,
    search_results_python_side
)

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


API_ROW_LIMIT = 40
REPORT_ROW_LIMIT = 200


def _tour_built() -> list[dict]:
    return [
        {
            'description': (
                'Sixty rows, each one refetching its author, publisher and reviews '
                'one query at a time.'
            ),
            'panel': 'Queries',
            'title': 'Books',
            'url': reverse('bookstore:book_list')
        },
        {
            'description': (
                'The same page rewritten with select_related, prefetch_related and '
                'database aggregates.'
            ),
            'panel': 'Queries',
            'title': 'Books (fixed)',
            'url': reverse('bookstore:book_list_optimized')
        },
        {
            'description': (
                'A count() per author, a rating average assembled in Python and a sort '
                'that never reaches the database.'
            ),
            'panel': 'Queries',
            'title': 'Authors',
            'url': reverse('bookstore:author_list')
        },
        {
            'description': (
                'Four levels deep: order, item, book, author, each level fetched inside '
                'the loop above it.'
            ),
            'panel': 'Queries',
            'title': 'Orders',
            'url': reverse('bookstore:order_list')
        },
        {
            'description': (
                'A view that spends most of its time in Python: nested loops, string '
                'concatenation and repeated sorts.'
            ),
            'panel': 'Profiling',
            'title': 'Reports',
            'url': reverse('bookstore:report')
        },
        {
            'description': (
                'Three unindexed LIKE scans over the whole table, deduplicated and '
                'ranked after the fact.'
            ),
            'panel': 'Queries',
            'title': 'Search',
            'url': reverse('bookstore:search')
        },
        {
            'description': (
                'Key-by-key cache traffic: get, set, get_many, has_key, delete and '
                'get_or_set on every request.'
            ),
            'panel': 'Cache',
            'title': 'Cache',
            'url': reverse('bookstore:cache')
        },
        {
            'description': (
                'Forty thousand throwaway dictionaries, an index over them and a list '
                'that never releases what it keeps.'
            ),
            'panel': 'Memory',
            'title': 'Memory',
            'url': reverse('bookstore:memory')
        },
        {
            'description': (
                'Lifetime spend per customer, computed by walking every order and every '
                'line item in Python.'
            ),
            'panel': 'Queries',
            'title': 'Customers',
            'url': reverse('bookstore:customer_list')
        }
    ]


def api_book_list_view(request: HttpRequest) -> JsonResponse:
    _ = request

    books = list(Book.objects.all()[:API_ROW_LIMIT])
    rows = []

    for book in books:
        row = {
            'author': book.author.name,
            'categories': [category.name for category in book.categories.all()],
            'price': float(book.price),
            'publisher': book.publisher.name,
            'rating': book.average_rating,
            'reviews': book.reviews.count(),
            'title': book.title
        }

        rows.append(row)

    payload = {'count': len(rows), 'rows': rows}

    return JsonResponse(payload)


def author_list_view(request: HttpRequest) -> HttpResponse:
    notes = [
        'Every author is loaded, then every book of every author, then every review of every book.',
        'author.books.count() adds one more query per row on top of the books already in memory.',
        'The average rating is folded in Python, so the database returns rows it did not need to.',
        'The ranking is a list.sort() after the fact, which means no ORDER BY and no LIMIT.'
    ]

    context = {
        'notes': notes,
        'page_kicker': 'Aggregation in the wrong place',
        'page_title': 'Authors',
        'rows': author_rows_python_side(),
        'total_authors': Author.objects.count(),
        'total_books': Book.objects.count()
    }

    return render(request, 'page/author_list.html', context)


def book_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    book = Book.objects.get(pk=pk)
    same_author = Book.objects.filter(author=Book.objects.get(pk=pk).author)
    same_publisher = Book.objects.filter(publisher=Book.objects.get(pk=pk).publisher)

    notes = [
        'The same book is fetched three times by primary key, once per related list.',
        'Each related list loads full rows, including the summary column nothing renders.',
        'The reviews are re-queried even though book.reviews already hangs off the instance.'
    ]

    context = {
        'book': book,
        'notes': notes,
        'page_kicker': 'Duplicate queries',
        'page_title': book.title,
        'related_by_author': list(same_author),
        'related_by_publisher': list(same_publisher),
        'reviews': list(Review.objects.filter(book=book))
    }

    return render(request, 'page/book_detail.html', context)


def book_list_optimized_view(request: HttpRequest) -> HttpResponse:
    notes = [
        (
            'select_related pulls the author, the publisher and the author\'s publisher '
            'into the same join.'
        ),
        'prefetch_related resolves categories and tags in one query each, not one per row.',
        'Count and Avg run as annotations, so no property opens a query during rendering.',
        'The totals come back from a single aggregate() instead of a Python loop.'
    ]

    context = {
        'books': book_rows_optimized(),
        'note_border': 'border-success',
        'note_title': 'What this page does instead',
        'notes': notes,
        'page_action_label': 'Back to the slow page',
        'page_action_url': reverse('bookstore:book_list'),
        'page_kicker': 'The same page, fixed',
        'page_title': 'Books (optimized)',
        'totals': catalog_totals_optimized()
    }

    return render(request, 'page/book_list_optimized.html', context)


def book_list_view(request: HttpRequest) -> HttpResponse:
    notes = [
        (
            'Book.objects.all() runs with no select_related, so each row refetches its '
            'author, that author\'s publisher and its own publisher.'
        ),
        'review_count and average_rating are properties, so each one opens another query per row.',
        (
            'categories and tags are read in the template without prefetch_related, adding '
            'two more queries per row.'
        ),
        'The totals are summed and averaged in Python after loading every book and every review.'
    ]

    context = {
        'books': book_rows_unoptimized(),
        'notes': notes,
        'page_action_label': 'Compare with the fixed page',
        'page_action_url': reverse('bookstore:book_list_optimized'),
        'page_kicker': 'N+1 queries',
        'page_title': 'Books',
        'totals': catalog_totals_python_side()
    }

    return render(request, 'page/book_list.html', context)


def cache_view(request: HttpRequest) -> HttpResponse:
    notes = [
        'Forty keys are read one at a time instead of through a single get_many.',
        'Every miss writes immediately, so a cold process pays a get and a set for each key.',
        'get_or_set falls back to a COUNT over the whole book table.',
        'A request_started receiver reads two more keys before the view even runs.'
    ]

    context = {
        'notes': notes,
        'page_kicker': 'Cache traffic',
        'page_title': 'Cache',
        'result': cache_thrash_run()
    }

    return render(request, 'page/cache.html', context)


def customer_list_view(request: HttpRequest) -> HttpResponse:
    notes = [
        'Every customer is loaded, then their orders, then the line items of each order.',
        'Spend is accumulated in Python rather than through Sum() on the line items.',
        'customer.orders.count() repeats work the loop above it has already done.',
        'The top rows are selected by sorting the whole list in memory.'
    ]

    context = {
        'notes': notes,
        'page_kicker': 'Nested relation walking',
        'page_title': 'Customers',
        'rows': customer_rows_python_side(),
        'total_customers': Customer.objects.count(),
        'total_orders': Order.objects.count()
    }

    return render(request, 'page/customer_list.html', context)


def dashboard_view(request: HttpRequest) -> HttpResponse:
    counts = {
        'authors': Author.objects.count(),
        'books': Book.objects.count(),
        'categories': Category.objects.count(),
        'customers': Customer.objects.count(),
        'orders': Order.objects.count(),
        'publishers': Publisher.objects.count(),
        'reviews': Review.objects.count(),
        'tags': Tag.objects.count()
    }

    notes = [
        'Eight separate COUNT queries run where one aggregate would do.',
        (
            'The publisher table calls author_count and book_count per row, so each row '
            'costs two more queries.'
        ),
        (
            'The review list reaches through review.book and review.book.author, adding '
            'two queries per entry.'
        ),
        (
            'Every page in the navigation is deliberately unoptimized. The fixed catalog '
            'page is the one exception.'
        )
    ]

    context = {
        'counts': counts,
        'notes': notes,
        'page_kicker': 'Kaleidoscope demo',
        'page_title': 'Dashboard',
        'publishers': publisher_rows_unoptimized(),
        'recent_reviews': review_rows_unoptimized(),
        'tour': _tour_built()
    }

    return render(request, 'page/dashboard.html', context)


def memory_view(request: HttpRequest) -> HttpResponse:
    notes = [
        (
            'Forty thousand dictionaries are built, each holding a list of six integers '
            'and a padded digest string.'
        ),
        'A second dictionary indexes the same rows by label, doubling the references held at once.',
        'A third list copies every digest out before a set collapses them.',
        (
            'A module-level list keeps four thousand of those rows after the response and '
            'never evicts them, so the process grows with every request.'
        )
    ]

    context = {
        'notes': notes,
        'page_kicker': 'Allocation churn',
        'page_title': 'Memory',
        'result': memory_churn_run()
    }

    return render(request, 'page/memory.html', context)


def order_list_view(request: HttpRequest) -> HttpResponse:
    notes = [
        (
            'The template walks order, item, book and author, and each level queries '
            'inside the loop above it.'
        ),
        'order.item_count and order.total each iterate the same items again from scratch.',
        'order.customer is read per card with no select_related on the queryset.',
        'The line total is computed per row in Python instead of as an F() expression.'
    ]

    context = {
        'notes': notes,
        'orders': order_rows_unoptimized(),
        'page_kicker': 'Four levels of N+1',
        'page_title': 'Orders',
        'total_orders': Order.objects.count()
    }

    return render(request, 'page/order_list.html', context)


def report_view(request: HttpRequest) -> HttpResponse:
    started = time.perf_counter()

    books = list(Book.objects.all()[:REPORT_ROW_LIMIT])
    reviews = list(Review.objects.all())

    histogram = {}
    revenue_by_publisher = {}
    revenue_by_title = {}

    for review in reviews:
        histogram[review.rating] = histogram.get(review.rating, 0) + 1

    for book in books:
        publisher_name = book.publisher.name
        revenue = 0.0

        for item in book.order_items.all():
            revenue += float(item.unit_price) * item.quantity

        carried = revenue_by_publisher.get(publisher_name, 0.0)
        revenue_by_publisher[publisher_name] = carried + revenue
        revenue_by_title[book.title] = revenue

    fingerprints = []

    for book in books:
        fingerprint = ''

        for review in book.reviews.all():
            fingerprint += f'{review.rating}:{review.reviewer_name[:3]}|'

        fingerprints.append(fingerprint)

    top_publishers = sorted(revenue_by_publisher.items(), key=lambda entry: entry[1], reverse=True)
    top_titles = sorted(revenue_by_title.items(), key=lambda entry: entry[1], reverse=True)

    notes = [
        'Every rating is counted in a Python loop instead of a values().annotate(Count()).',
        'Revenue is rebuilt per book by fetching that book\'s order items inside the loop.',
        (
            'The reviews of each book are fetched a second time to build a string by '
            'repeated concatenation.'
        ),
        'Turn on the Line Profiler panel and reload to see which of these lines costs the time.'
    ]

    context = {
        'duration_ms': round((time.perf_counter() - started) * 1000, 1),
        'fingerprint_length': sum(len(fingerprint) for fingerprint in fingerprints),
        'histogram': sorted(histogram.items()),
        'notes': notes,
        'page_kicker': 'Time spent in Python',
        'page_title': 'Reports',
        'top_publishers': top_publishers[:10],
        'top_titles': top_titles[:10]
    }

    return render(request, 'page/report.html', context)


def search_view(request: HttpRequest) -> HttpResponse:
    term = request.GET.get('q', 'the')

    notes = [
        (
            'Three icontains queries scan the whole table, one for the title, one for the '
            'summary and one for the author name.'
        ),
        'No column in the schema carries db_index, so none of the three can use an index.',
        (
            'The results are concatenated and deduplicated in Python instead of combined '
            'with Q objects.'
        ),
        'Each surviving row then queries its author, its publisher and its reviews.'
    ]

    context = {
        'notes': notes,
        'page_kicker': 'Unindexed scans',
        'page_title': 'Search',
        'rows': search_results_python_side(term),
        'term': term
    }

    return render(request, 'page/search.html', context)
