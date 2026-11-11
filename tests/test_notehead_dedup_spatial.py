"""Comparação estrita da deduplicação espacial com a regra legada."""

import random

import pytest

from fluteomr.notes import NoteheadObservation, _deduplicate_candidates
from fluteomr.staff_detection import Region


def _legacy(candidates, spacing):
    chosen = []
    for candidate in sorted(
        candidates, key=lambda c: (c.stem_present, c.shape_score), reverse=True
    ):
        if any(
            abs(candidate.center_x - previous.center_x) < 0.9 * spacing
            and (
                abs(candidate.center_y - previous.center_y) < 0.65 * spacing
                or (
                    abs(candidate.center_x - previous.center_x) < 0.35 * spacing
                    and abs(candidate.center_y - previous.center_y) < 1.1 * spacing
                )
            )
            for previous in chosen
        ):
            continue
        chosen.append(candidate)
    return tuple(sorted(chosen, key=lambda c: c.center_x))


def _candidate(x, y, rng):
    return NoteheadObservation(
        x,
        y,
        Region(x - 4, y - 2, x + 4, y + 2),
        rng.choice(("hollow", "filled")),
        rng.choice((True, False)),
        rng.choice((0.1, 0.3, 0.5, 0.9)),
        (),
    )


@pytest.mark.parametrize("spacing", [0, 4, 8, 12.5, 16, 20, 40])
@pytest.mark.parametrize("seed", [0, 1, 2, 8])
def test_spatial_deduplication_is_exactly_equivalent_to_legacy(spacing, seed):
    rng = random.Random(seed)
    candidates = [
        _candidate(
            rng.randrange(-60, 1600),
            rng.randrange(-35, 130),
            rng,
        )
        for _ in range(480)
    ]
    assert _deduplicate_candidates(candidates, spacing) == _legacy(candidates, spacing)


def test_edge_cases_and_equal_priority_preserve_stable_order():
    rng = random.Random(414)
    for spacing in (6, 9, 14.5, 25):
        candidates = [
            _candidate(x, y, rng) for x in range(-10, 300, 3) for y in (20, 21, 22)
        ]
        assert _deduplicate_candidates(candidates, spacing) == _legacy(
            candidates, spacing
        )
