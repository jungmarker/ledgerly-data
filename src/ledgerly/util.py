"""Shared helpers: deterministic IDs and date math."""
from datetime import date, datetime, timedelta

import numpy as np

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


class IdFactory:
    """Salesforce-style 18-character IDs (3-char object prefix + 15 chars), deterministic per seed."""

    PREFIX = {"account": "001", "contact": "003", "opportunity": "006", "lead": "00Q", "user": "005",
              "case": "500", "subscription": "a0S", "invoice": "a0I"}

    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.seen: set[str] = set()

    def new(self, kind: str) -> str:
        while True:
            body = "".join(_ALPHABET[i] for i in self.rng.integers(0, len(_ALPHABET), 15))
            sid = self.PREFIX[kind] + body
            if sid not in self.seen:
                self.seen.add(sid)
                return sid


def month_starts(start: date, end: date) -> list[date]:
    out, d = [], date(start.year, start.month, 1)
    while d <= end:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError(d)


def random_time(rng: np.random.Generator, d: date) -> datetime:
    """A business-hours-weighted timestamp on day d."""
    hour = int(np.clip(rng.normal(13, 3), 6, 22))
    return datetime(d.year, d.month, d.day, hour, int(rng.integers(0, 60)), int(rng.integers(0, 60)))


def days(n: float) -> timedelta:
    return timedelta(days=float(n))
