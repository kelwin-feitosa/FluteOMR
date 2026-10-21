"""Entradas fora do contrato não podem virar XML aparentemente suportado."""

from dataclasses import replace

import pytest

from fluteomr.music import (
    Clef,
    Duration,
    Measure,
    MusicPart,
    MusicScore,
    Note,
    Pitch,
    TimeSignature,
)
from fluteomr.musicxml import to_musicxml
from fluteomr.staff_detection import Region


def _score():
    notes = tuple(
        Note(Pitch("E", 4), Duration("quarter"), Region(1, 1, 9, 9), 0, "filled")
        for _ in range(4)
    )
    measure = Measure(1, notes, TimeSignature(4, 4, "configuration"), "configuration")
    return MusicScore(
        (
            MusicPart(
                "P1",
                "Solo",
                "configuration",
                (0,),
                Clef("treble", "configuration"),
                (measure,),
            ),
        )
    )


@pytest.mark.parametrize(
    "case", ["clef", "duration", "pitch", "beam", "part_id", "measure_number"]
)
def test_unsupported_or_inconsistent_model_is_rejected_before_serialization(case):
    score = _score()
    part = score.parts[0]
    measure = part.measures[0]
    if case == "clef":
        score = replace(
            score, parts=(replace(part, clef=Clef("bass", "configuration")),)
        )
    elif case in ("duration", "pitch"):
        change = (
            {"duration": Duration("whole")}
            if case == "duration"
            else {"pitch": Pitch("H", 4)}
        )
        note = replace(measure.notes[0], **change)
        score = replace(
            score,
            parts=(
                replace(
                    part, measures=(replace(measure, notes=(note, *measure.notes[1:])),)
                ),
            ),
        )
    elif case == "beam":
        notes = tuple(
            replace(
                measure.notes[0],
                duration=Duration("eighth"),
                beam="invalid" if i == 0 else None,
            )
            for i in range(8)
        )
        score = replace(
            score, parts=(replace(part, measures=(replace(measure, notes=notes),)),)
        )
    elif case == "part_id":
        score = replace(score, parts=(part, part))
    else:
        score = replace(score, parts=(replace(part, measures=(measure, measure)),))
    with pytest.raises(ValueError):
        to_musicxml(score)
