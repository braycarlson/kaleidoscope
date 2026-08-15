from __future__ import annotations

from django.db import models


class Author(models.Model):
    biography = models.TextField(default='')
    birth_year = models.IntegerField(default=1950)
    country = models.CharField(max_length=64)
    email = models.CharField(max_length=128)
    name = models.CharField(max_length=128)

    publisher = models.ForeignKey(
        'bookstore.Publisher',
        on_delete=models.CASCADE,
        related_name='authors'
    )

    class Meta:
        db_table = 'bookstore_author'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    @property
    def average_rating(self) -> float:
        ratings = []

        for book in self.books.all():
            for review in book.reviews.all():
                ratings.append(review.rating)

        if not ratings:
            return 0.0

        return round(sum(ratings) / len(ratings), 2)

    @property
    def book_count(self) -> int:
        return self.books.count()

    @property
    def revenue(self) -> float:
        total = 0.0

        for book in self.books.all():
            for item in book.order_items.all():
                total += float(item.unit_price) * item.quantity

        return round(total, 2)


class Book(models.Model):
    author = models.ForeignKey('bookstore.Author', on_delete=models.CASCADE, related_name='books')
    categories = models.ManyToManyField('bookstore.Category', related_name='books')
    isbn = models.CharField(max_length=32)
    page_count = models.IntegerField(default=0)
    price = models.DecimalField(decimal_places=2, max_digits=8)
    published_on = models.DateField()
    summary = models.TextField(default='')
    tags = models.ManyToManyField('bookstore.Tag', related_name='books')
    title = models.CharField(max_length=256)

    publisher = models.ForeignKey(
        'bookstore.Publisher',
        on_delete=models.CASCADE,
        related_name='books'
    )

    class Meta:
        db_table = 'bookstore_book'
        ordering = ['title']

    def __str__(self) -> str:
        return self.title

    @property
    def average_rating(self) -> float:
        ratings = [review.rating for review in self.reviews.all()]

        if not ratings:
            return 0.0

        return round(sum(ratings) / len(ratings), 2)

    @property
    def category_names(self) -> str:
        return ', '.join(category.name for category in self.categories.all())

    @property
    def copies_sold(self) -> int:
        return sum(item.quantity for item in self.order_items.all())

    @property
    def review_count(self) -> int:
        return self.reviews.count()


class Category(models.Model):
    description = models.TextField(default='')
    name = models.CharField(max_length=64)
    slug = models.CharField(max_length=64)

    class Meta:
        db_table = 'bookstore_category'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Customer(models.Model):
    city = models.CharField(max_length=64)
    country = models.CharField(max_length=64)
    email = models.CharField(max_length=128)
    joined_on = models.DateField()
    name = models.CharField(max_length=128)
    notes = models.TextField(default='')

    class Meta:
        db_table = 'bookstore_customer'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    @property
    def lifetime_value(self) -> float:
        total = 0.0

        for order in self.orders.all():
            for item in order.items.all():
                total += float(item.unit_price) * item.quantity

        return round(total, 2)

    @property
    def order_count(self) -> int:
        return self.orders.count()


class Order(models.Model):
    fulfillment_notes = models.TextField(default='')
    placed_on = models.DateField()
    reference = models.CharField(max_length=32)
    status = models.CharField(max_length=32)

    customer = models.ForeignKey(
        'bookstore.Customer',
        on_delete=models.CASCADE,
        related_name='orders'
    )

    class Meta:
        db_table = 'bookstore_order'
        ordering = ['-placed_on']

    def __str__(self) -> str:
        return self.reference

    @property
    def item_count(self) -> int:
        return self.items.count()

    @property
    def total(self) -> float:
        total = 0.0

        for item in self.items.all():
            total += float(item.unit_price) * item.quantity

        return round(total, 2)


class OrderItem(models.Model):
    book = models.ForeignKey('bookstore.Book', on_delete=models.CASCADE, related_name='order_items')
    order = models.ForeignKey('bookstore.Order', on_delete=models.CASCADE, related_name='items')
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(decimal_places=2, max_digits=8)

    class Meta:
        db_table = 'bookstore_order_item'
        ordering = ['id']

    def __str__(self) -> str:
        return f'{self.order.reference} / {self.book.title}'

    @property
    def line_total(self) -> float:
        return round(float(self.unit_price) * self.quantity, 2)


class Publisher(models.Model):
    city = models.CharField(max_length=64)
    country = models.CharField(max_length=64)
    description = models.TextField(default='')
    founded_year = models.IntegerField(default=1900)
    name = models.CharField(max_length=128)

    class Meta:
        db_table = 'bookstore_publisher'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    @property
    def author_count(self) -> int:
        return self.authors.count()

    @property
    def book_count(self) -> int:
        return self.books.count()


class Review(models.Model):
    body = models.TextField(default='')
    book = models.ForeignKey('bookstore.Book', on_delete=models.CASCADE, related_name='reviews')
    created_on = models.DateField()
    rating = models.IntegerField(default=5)
    reviewer_name = models.CharField(max_length=128)

    class Meta:
        db_table = 'bookstore_review'
        ordering = ['-created_on']

    def __str__(self) -> str:
        return f'{self.reviewer_name} / {self.rating}'


class Tag(models.Model):
    name = models.CharField(max_length=64)
    slug = models.CharField(max_length=64)

    class Meta:
        db_table = 'bookstore_tag'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name
