"""Shape prefix is pixel- and score-equivalent to the original implementation."""

import random

import pytest

from fluteomr.notes import (
    _horizontal_ink_prefix,
    _offset_spans,
    _shape,
    _shape_from_prefix,
    detect_noteheads,
)
from fluteomr.staff_detection import Region, Staff, StaffLine


def _masks(rx, ry):
    core = tuple(
        (dx, dy)
        for dy in range(-ry, ry + 1)
        for dx in range(-rx, rx + 1)
        if (dx / rx) ** 2 + (dy / ry) ** 2 <= 0.30
    )
    rim = tuple(
        (dx, dy)
        for dy in range(-ry, ry + 1)
        for dx in range(-rx, rx + 1)
        if 0.55 <= (dx / rx) ** 2 + (dy / ry) ** 2 <= 1.15
    )
    sides = tuple(
        tuple(
            (dx, dy)
            for dx, dy in rim
            if dx * sign > 0 and abs(dx) >= 0.55 * rx and abs(dy) <= 0.6 * ry
        )
        for sign in (-1, 1)
    )
    return core, rim, sides


@pytest.mark.parametrize("rx,ry", [(3, 2), (4, 3), (7, 5), (11, 7)])
@pytest.mark.parametrize("seed", [1, 8, 20])
def test_prefix_shape_exact_matches_legacy_randomized(rx, ry, seed):
    rng = random.Random(seed)
    width = 44
    height = 39
    core, rim, sides = _masks(rx, ry)
    side_spans = tuple(_offset_spans(s) for s in sides)
    prepared = [
        bytearray(rng.randrange(2) for _ in range(width * height)),
        bytearray([0] * (width * height)),
        bytearray([1] * (width * height)),
    ]
    for ink in prepared:
        prefix = _horizontal_ink_prefix(ink, width, height)
        for y in range(-1, height + 1, 2):
            for x in range(-1, width + 1, 2):
                old = _shape(
                    ink, width, height, x, y, rx, ry, core, rim, sides
                )
                new = _shape_from_prefix(
                    prefix, width, height, x, y, rx, ry, core, rim, sides,
                    _offset_spans(core), _offset_spans(rim), side_spans,
                )
                assert new == old, (rx, ry, seed, x, y, old, new)


def test_spans_count_only_original_offset_pixels():
    rng = random.Random(77)
    width, height = 23, 19
    ink = bytearray(rng.randrange(2) for _ in range(width * height))
    prefix = _horizontal_ink_prefix(ink, width, height)
    for rx, ry in ((3, 2), (6, 3)):
        core, rim, sides = _masks(rx, ry)
        for offsets in (core, rim, *sides):
            expected = sum(ink[(9 + dy) * width + 11 + dx] for dx, dy in offsets)
            actual = sum(
                prefix[(9 + dy) * (width + 1) + 11 + right + 1]
                - prefix[(9 + dy) * (width + 1) + 11 + left]
                for dy, spans in _offset_spans(offsets)
                for left, right in spans
            )
            assert actual == expected
