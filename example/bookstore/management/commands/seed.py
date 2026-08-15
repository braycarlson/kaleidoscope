from __future__ import annotations

import datetime
import random

from typing_extensions import TYPE_CHECKING

from django.core.management.base import BaseCommand
from django.db import transaction

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

if TYPE_CHECKING:
    from typing_extensions import Any


AUTHOR_COUNT = 90
BOOK_COUNT = 400
CUSTOMER_COUNT = 120
ORDER_COUNT = 260
ORDER_ITEM_COUNT = 800
PUBLISHER_COUNT = 18
REVIEW_COUNT = 1_400

BATCH_SIZE = 500
SEED = 1337

ADJECTIVES = [
    'Amber', 'Ancient', 'Bitter', 'Bright', 'Broken', 'Crimson', 'Distant', 'Electric', 'Empty',
    'Endless', 'Frozen', 'Gilded', 'Glass', 'Golden', 'Hollow', 'Hidden', 'Iron', 'Lonely',
    'Northern', 'Patient', 'Quiet', 'Restless', 'Salt', 'Silent', 'Silver', 'Slow', 'Stubborn',
    'Sudden', 'Tender', 'Velvet', 'Wandering', 'Winter'
]

CATEGORY_NAMES = [
    'Biography', 'Essays', 'Fantasy', 'History', 'Horror', 'Literary Fiction', 'Mystery',
    'Philosophy', 'Poetry', 'Science', 'Science Fiction', 'Travel'
]

CITIES = [
    'Aarhus', 'Bergen', 'Bristol', 'Calgary', 'Dunedin', 'Edinburgh', 'Ghent', 'Halifax', 'Kyoto',
    'Lisbon', 'Ljubljana', 'Montreal', 'Porto', 'Reykjavik', 'Tallinn', 'Trieste', 'Utrecht',
    'Valparaiso', 'Victoria', 'Wellington'
]

COUNTRIES = [
    'Australia', 'Belgium', 'Canada', 'Chile', 'Denmark', 'Estonia', 'Iceland', 'Italy', 'Japan',
    'Netherlands', 'New Zealand', 'Norway', 'Portugal', 'Slovenia', 'United Kingdom'
]

NOUNS = [
    'Anchor', 'Archive', 'Atlas', 'Bell', 'Cartographer', 'Chorus', 'Compass', 'Corridor',
    'Engine', 'Garden', 'Harbour', 'Inventory', 'Lantern', 'Ledger', 'Lighthouse', 'Machine',
    'Meridian', 'Observatory', 'Orchard', 'Parallel', 'Quarry', 'Register', 'Rehearsal', 'Signal',
    'Station', 'Telegram', 'Threshold', 'Tide', 'Vault', 'Window'
]

PROSE = [
    'The catalogue was never meant to be read in order.',
    'Every record here carries the residue of the hand that filed it.',
    'A shelf is an argument about what deserves to be remembered.',
    'The margins hold more than the pages they interrupt.',
    'Nothing in the collection agrees on a single accounting of the year.',
    'A reader arrives late and leaves with the wrong volume.',
    'The index was compiled twice and reconciled once.',
    'Errors propagate faster than corrections in any catalogue.',
    'The binding outlives the argument it was made to protect.',
    'Provenance is the only field nobody fills in honestly.'
]

STATUSES = ['cancelled', 'delivered', 'packed', 'pending', 'refunded', 'shipped']

SURNAMES = [
    'Abendroth', 'Baranov', 'Calloway', 'Delacroix', 'Eberhardt', 'Falkner', 'Grimaldi',
    'Havelock', 'Ingersoll', 'Jarnefelt', 'Kowalski', 'Lindqvist', 'Marchetti', 'Nakamura',
    'Ostrowski', 'Pemberton', 'Quintero', 'Rasmussen', 'Solberg', 'Thackeray', 'Ueda',
    'Vasquez', 'Whitlock', 'Yarnell', 'Zabriskie'
]

TAG_NAMES = [
    'award-winner', 'backlist', 'bestseller', 'boxed-set', 'debut', 'ebook', 'first-edition',
    'gift', 'hardcover', 'illustrated', 'large-print', 'new-release', 'paperback', 'reissue',
    'signed', 'staff-pick', 'translated', 'unabridged'
]

FIRST_NAMES = [
    'Adela', 'Bram', 'Cassia', 'Dermot', 'Elke', 'Fenna', 'Goran', 'Hazel', 'Ines', 'Joris',
    'Kaisa', 'Lior', 'Mirren', 'Nils', 'Odile', 'Piet', 'Rasha', 'Soren', 'Tova', 'Ulla',
    'Vesna', 'Wren', 'Yannick', 'Zofia'
]


class Command(BaseCommand):
    help = 'Populate the demo database with fake bookstore records.'

    def _authors_created(
        self,
        generator: random.Random,
        publishers: list[Publisher]
    ) -> list[Author]:
        authors = []

        for index in range(AUTHOR_COUNT):
            name = f'{generator.choice(FIRST_NAMES)} {generator.choice(SURNAMES)}'

            author = Author(
                biography=self._prose_built(generator, 9),
                birth_year=generator.randint(1920, 1995),
                country=generator.choice(COUNTRIES),
                email=f'author{index}@example.test',
                name=name,
                publisher=generator.choice(publishers)
            )

            authors.append(author)

        return Author.objects.bulk_create(authors, batch_size=BATCH_SIZE)

    def _books_created(
        self,
        generator: random.Random,
        authors: list[Author],
        publishers: list[Publisher]
    ) -> list[Book]:
        books = []

        for index in range(BOOK_COUNT):
            author = generator.choice(authors)
            title = self._title_built(generator)

            book = Book(
                author=author,
                isbn=f'978-{generator.randint(100000000, 999999999)}',
                page_count=generator.randint(96, 940),
                price=generator.randint(799, 6499) / 100,
                published_on=self._date_built(generator, 1998, 2026),
                publisher=generator.choice(publishers),
                summary=self._prose_built(generator, 12),
                title=f'{title} ({index + 1})'
            )

            books.append(book)

        return Book.objects.bulk_create(books, batch_size=BATCH_SIZE)

    def _categories_created(self, generator: random.Random) -> list[Category]:
        categories = []

        for name in CATEGORY_NAMES:
            category = Category(
                description=self._prose_built(generator, 4),
                name=name,
                slug=name.lower().replace(' ', '-')
            )

            categories.append(category)

        return Category.objects.bulk_create(categories, batch_size=BATCH_SIZE)

    def _customers_created(self, generator: random.Random) -> list[Customer]:
        customers = []

        for index in range(CUSTOMER_COUNT):
            name = f'{generator.choice(FIRST_NAMES)} {generator.choice(SURNAMES)}'

            customer = Customer(
                city=generator.choice(CITIES),
                country=generator.choice(COUNTRIES),
                email=f'customer{index}@example.test',
                joined_on=self._date_built(generator, 2016, 2026),
                name=name,
                notes=self._prose_built(generator, 5)
            )

            customers.append(customer)

        return Customer.objects.bulk_create(customers, batch_size=BATCH_SIZE)

    def _date_built(
        self,
        generator: random.Random,
        start_year: int,
        end_year: int
    ) -> datetime.date:
        year = generator.randint(start_year, end_year)
        month = generator.randint(1, 12)
        day = generator.randint(1, 28)

        return datetime.date(year, month, day)

    def _links_created(
        self,
        generator: random.Random,
        books: list[Book],
        categories: list[Category],
        tags: list[Tag]
    ) -> None:
        category_links = []
        tag_links = []

        category_model = Book.categories.through
        tag_model = Book.tags.through

        for book in books:
            for category in generator.sample(categories, generator.randint(1, 3)):
                link = category_model(book_id=book.pk, category_id=category.pk)
                category_links.append(link)

            for tag in generator.sample(tags, generator.randint(2, 4)):
                link = tag_model(book_id=book.pk, tag_id=tag.pk)
                tag_links.append(link)

        category_model.objects.bulk_create(category_links, batch_size=BATCH_SIZE)
        tag_model.objects.bulk_create(tag_links, batch_size=BATCH_SIZE)

    def _order_items_created(
        self,
        generator: random.Random,
        books: list[Book],
        orders: list[Order]
    ) -> list[OrderItem]:
        items = []

        for _ in range(ORDER_ITEM_COUNT):
            book = generator.choice(books)

            item = OrderItem(
                book=book,
                order=generator.choice(orders),
                quantity=generator.randint(1, 5),
                unit_price=book.price
            )

            items.append(item)

        return OrderItem.objects.bulk_create(items, batch_size=BATCH_SIZE)

    def _orders_created(self, generator: random.Random, customers: list[Customer]) -> list[Order]:
        orders = []

        for index in range(ORDER_COUNT):
            order = Order(
                customer=generator.choice(customers),
                fulfillment_notes=self._prose_built(generator, 3),
                placed_on=self._date_built(generator, 2023, 2026),
                reference=f'ORD-{index + 1000:05d}',
                status=generator.choice(STATUSES)
            )

            orders.append(order)

        return Order.objects.bulk_create(orders, batch_size=BATCH_SIZE)

    def _prose_built(self, generator: random.Random, sentences: int) -> str:
        parts = [generator.choice(PROSE) for _ in range(sentences)]

        return ' '.join(parts)

    def _publishers_created(self, generator: random.Random) -> list[Publisher]:
        publishers = []

        for index in range(PUBLISHER_COUNT):
            name = f'{generator.choice(ADJECTIVES)} {generator.choice(NOUNS)} Press'

            publisher = Publisher(
                city=generator.choice(CITIES),
                country=generator.choice(COUNTRIES),
                description=self._prose_built(generator, 8),
                founded_year=generator.randint(1890, 2015),
                name=f'{name} {index + 1}'
            )

            publishers.append(publisher)

        return Publisher.objects.bulk_create(publishers, batch_size=BATCH_SIZE)

    def _reviews_created(self, generator: random.Random, books: list[Book]) -> list[Review]:
        reviews = []

        for _ in range(REVIEW_COUNT):
            name = f'{generator.choice(FIRST_NAMES)} {generator.choice(SURNAMES)}'

            review = Review(
                body=self._prose_built(generator, 6),
                book=generator.choice(books),
                created_on=self._date_built(generator, 2020, 2026),
                rating=generator.randint(1, 5),
                reviewer_name=name
            )

            reviews.append(review)

        return Review.objects.bulk_create(reviews, batch_size=BATCH_SIZE)

    def _tags_created(self) -> list[Tag]:
        tags = []

        for name in TAG_NAMES:
            tag = Tag(name=name, slug=name)
            tags.append(tag)

        return Tag.objects.bulk_create(tags, batch_size=BATCH_SIZE)

    def _title_built(self, generator: random.Random) -> str:
        shape = generator.randint(0, 2)

        if shape == 0:
            return f'The {generator.choice(ADJECTIVES)} {generator.choice(NOUNS)}'

        if shape == 1:
            head = generator.choice(NOUNS)
            tail = f'{generator.choice(ADJECTIVES)} {generator.choice(NOUNS)}'

            return f'{head} of the {tail}'

        return f'A {generator.choice(ADJECTIVES)} {generator.choice(NOUNS)}'

    def _truncated(self) -> None:
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        Review.objects.all().delete()
        Book.objects.all().delete()
        Author.objects.all().delete()
        Customer.objects.all().delete()
        Publisher.objects.all().delete()
        Category.objects.all().delete()
        Tag.objects.all().delete()

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        _ = args
        _ = options

        generator = random.Random(SEED)

        self._truncated()

        categories = self._categories_created(generator)
        publishers = self._publishers_created(generator)
        tags = self._tags_created()

        authors = self._authors_created(generator, publishers)
        books = self._books_created(generator, authors, publishers)
        customers = self._customers_created(generator)
        orders = self._orders_created(generator, customers)

        self._links_created(generator, books, categories, tags)
        self._order_items_created(generator, books, orders)
        self._reviews_created(generator, books)

        self.stdout.write(f'authors {len(authors)}')
        self.stdout.write(f'books {len(books)}')
        self.stdout.write(f'customers {len(customers)}')
        self.stdout.write(f'orders {len(orders)}')
        self.stdout.write(f'publishers {len(publishers)}')
