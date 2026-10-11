from __future__ import annotations

from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=64)

    class Meta:
        app_label = 'testapp'

    def __str__(self) -> str:
        return self.name


class Book(models.Model):
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='books')
    title = models.CharField(max_length=64)

    class Meta:
        app_label = 'testapp'

    def __str__(self) -> str:
        return self.title
