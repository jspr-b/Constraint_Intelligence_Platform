"""Interval arithmetic on minute ranges [start, end). Intervals are sorted and disjoint."""

from collections.abc import Iterable

Interval = tuple[float, float]


def normalise(items: Iterable[Interval]) -> list[Interval]:
    """Sort and merge overlapping or touching intervals; drop empty ones."""
    out: list[Interval] = []
    for start, end in sorted(i for i in items if i[1] > i[0]):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def intersect(a: Iterable[Interval], b: Iterable[Interval]) -> list[Interval]:
    a_n, b_n = normalise(a), normalise(b)
    out: list[Interval] = []
    i = j = 0
    while i < len(a_n) and j < len(b_n):
        start, end = max(a_n[i][0], b_n[j][0]), min(a_n[i][1], b_n[j][1])
        if end > start:
            out.append((start, end))
        if a_n[i][1] < b_n[j][1]:
            i += 1
        else:
            j += 1
    return out


def subtract(a: Iterable[Interval], b: Iterable[Interval]) -> list[Interval]:
    """Parts of ``a`` not covered by ``b``."""
    out: list[Interval] = []
    b_n = normalise(b)
    for start, end in normalise(a):
        cursor = start
        for b_start, b_end in b_n:
            if b_end <= cursor or b_start >= end:
                continue
            if b_start > cursor:
                out.append((cursor, b_start))
            cursor = max(cursor, b_end)
        if cursor < end:
            out.append((cursor, end))
    return out


def total(items: Iterable[Interval]) -> float:
    return sum(end - start for start, end in normalise(items))
