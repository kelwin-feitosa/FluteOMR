"""MusicXML 4.0: níveis independentes de feixes, incluindo hooks.

Os exemplos musicais são criados à mão, sem depender do detector de tinta.
"""

from dataclasses import replace
from fractions import Fraction
from xml.etree import ElementTree as ET

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


def _score(events: tuple[tuple[str, tuple[tuple[int, str], ...]], ...]):
    notes = tuple(
        Note(
            Pitch(("E", "F", "G", "A")[index % 4], 5),
            Duration(kind),
            Region(20 + 25 * index, 60, 31 + 25 * index, 68),
            0,
            "filled",
            beam_levels=levels,
        )
        for index, (kind, levels) in enumerate(events)
    )
    measure = Measure(1, notes, TimeSignature(1, 4, "configuration"), "user")
    return MusicScore(
        (
            MusicPart(
                "P1",
                "Flute",
                "configuration",
                (0,),
                Clef("treble", "configuration"),
                (measure,),
            ),
        )
    )


@pytest.mark.parametrize(
    ("kind", "levels", "expected_second"),
    [
        (
            ("eighth", "sixteenth", "sixteenth"),
            (
                ((1, "begin"),),
                ((1, "continue"), (2, "begin")),
                ((1, "end"), (2, "end")),
            ),
            (None, "begin", "end"),
        ),
        (
            ("sixteenth", "sixteenth", "eighth"),
            (
                ((1, "begin"), (2, "begin")),
                ((1, "continue"), (2, "end")),
                ((1, "end"),),
            ),
            ("begin", "end", None),
        ),
        (
            ("sixteenth", "eighth", "sixteenth"),
            (
                ((1, "begin"), (2, "forward hook")),
                ((1, "continue"),),
                ((1, "end"), (2, "backward hook")),
            ),
            ("forward hook", None, "backward hook"),
        ),
    ],
)
def test_mixed_rhythm_serializes_correct_second_beam_levels(
    kind, levels, expected_second
):
    score = _score(tuple(zip(kind, levels, strict=True)))
    assert score.issues() == ()
    assert sum(
        note.duration.quarters for note in score.parts[0].measures[0].notes
    ) == Fraction(1)
    root = ET.fromstring(to_musicxml(score))
    assert root.findtext("./part/measure/attributes/divisions") == "4"
    notes = root.findall("./part/measure/note")
    assert [note.findtext("duration") for note in notes] == [
        "2" if item == "eighth" else "1" for item in kind
    ]
    assert [note.findtext("type") for note in notes] == [
        "eighth" if item == "eighth" else "16th" for item in kind
    ]
    assert [
        note.find("beam[@number='1']").text for note in notes
    ] == ["begin", "continue", "end"]
    assert [
        (b.text if (b := note.find("beam[@number='2']")) is not None else None)
        for note in notes
    ] == list(expected_second)


@pytest.mark.parametrize(
    ("events", "diagnostic"),
    [
        (
            (
                ("sixteenth", ((1, "begin"),)),
                ("sixteenth", ((1, "end"), (2, "backward hook"))),
                ("eighth", ()),
            ),
            "secondary_beam_missing",
        ),
        (
            (
                ("eighth", ((1, "begin"), (2, "begin"))),
                ("eighth", ((1, "end"), (2, "end"))),
            ),
            "secondary_beam_invalid",
        ),
        (
            (
                ("sixteenth", ((2, "forward hook"),)),
                ("eighth", ()),
                ("eighth", ()),
            ),
            "secondary_beam_invalid",
        ),
        (
            (
                ("sixteenth", ((1, "begin"), (2, "begin"))),
                ("eighth", ((1, "continue"),)),
                ("sixteenth", ((1, "end"), (2, "end"))),
            ),
            "secondary_beam_interrupted",
        ),
        (
            (
                ("sixteenth", ((1, "begin"), (1, "end"), (2, "forward hook"))),
                ("eighth", ((1, "end"),)),
                ("eighth", ()),
            ),
            "beam_levels_invalid",
        ),
    ],
)
def test_invalid_or_ambiguous_beam_levels_rejected(events, diagnostic):
    score = _score(events)
    assert any(diagnostic in issue for issue in score.issues())
    with pytest.raises(ValueError, match="transcrição incompleta"):
        to_musicxml(score)


def test_conflicting_legacy_primary_beam_is_not_silently_discarded():
    score = _score(
        (
            ("sixteenth", ((1, "begin"), (2, "forward hook"))),
            ("eighth", ((1, "continue"),)),
            ("sixteenth", ((1, "end"), (2, "backward hook"))),
        )
    )
    part = score.parts[0]
    measure = part.measures[0]
    first = replace(measure.notes[0], beam="end")
    measure = replace(measure, notes=(first, *measure.notes[1:]))
    score = replace(score, parts=(replace(part, measures=(measure,)),))
    assert any("beam_primary_conflict" in x for x in score.issues())


def test_legacy_complete_sixteenths_still_write_both_levels():
    notes = tuple(
        Note(
            Pitch("E", 5),
            Duration("sixteenth"),
            Region(index * 15, 50, index * 15 + 10, 60),
            0,
            "filled",
            beam=("begin", "continue", "continue", "end")[index],
        )
        for index in range(4)
    )
    measure = Measure(1, notes, TimeSignature(1, 4, "configuration"), "user")
    score = MusicScore(
        (MusicPart("P1", "Flute", "configuration", (0,), Clef("treble", "user"), (measure,)),)
    )
    assert score.issues() == ()
    root = ET.fromstring(to_musicxml(score))
    assert [el.text for el in root.findall("./part/measure/note/beam[@number='2']")] == [
        "begin",
        "continue",
        "continue",
        "end",
    ]
