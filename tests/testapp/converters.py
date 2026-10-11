from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Color:
    name: str


class ColorConverter:
    regex = '[a-z]{3,12}'

    def to_python(self, value: str) -> Color:
        return Color(name=value)

    def to_url(self, value: Color) -> str:
        return value.name
