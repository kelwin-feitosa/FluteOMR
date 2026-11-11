"""Conservadorismo do reconhecimento de dois feixes e semicolcheias MusicXML."""

from dataclasses import replace
from fractions import Fraction
from xml.etree import ElementTree as ET

import pytest
from PIL import ImageDraw

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
from fluteomr.notes import detect_noteheads
from fluteomr.rhythm import detect_rhythm_evidence
from fluteomr.staff_detection import Region, detect_staffs
from fluteomr.symbols import BarlineCandidate, linked_stems
from fluteomr.transcription import transcribe_one_measure
from tests.test_eighths import _page


def _draw_secondary(image, a, b, *, spacing=16, length=1.0, thickness=4):
    """Traço de teste independente da lógica geométrica do reconhecedor."""
    radius_x = round(0.65 * spacing)

    def tip(x, degree):
        return (
            x - radius_x + 1,
            138 - round(degree * spacing / 2) + round(3.3 * spacing),
        )

    x1, y1 = tip(*a)
    x2, y2 = tip(*b)
    offset = -13
    ImageDraw.Draw(image).line(
        (
            x1,
            y1 + offset,
            round(x1 + length * (x2 - x1)),
            round(y1 + length * (y2 - y1)) + offset,
        ),
        fill="black",
        width=thickness,
    )


def _four_beamed():
    return (
        (145, 9, "eighth", "down"),
        (215, 8, "eighth", "down"),
        (285, 7, "eighth", "down"),
        (355, 6, "eighth", "down"),
    )


def test_one_secondary_pair_only_promotes_its_connected_notes():
    notes = _four_beamed()
    image = _page(notes, beam_groups=((0, 1, 2, 3),))
    _draw_secondary(image, notes[0][:2], notes[1][:2])
    score = transcribe_one_measure(image, measure_left=110, measure_right=410, beats=1)
    events = score.parts[0].measures[0].notes
    assert len(events) == 4
    assert [note.duration.kind for note in events] == [
        "sixteenth",
        "sixteenth",
        "eighth",
        "eighth",
    ]
    assert [note.beam_levels for note in events] == [
        ((1, "begin"), (2, "begin")),
        ((1, "continue"), (2, "end")),
        ((1, "continue"),),
        ((1, "end"),),
    ]
    # 1,5 semínimas em compasso 1/4: recusar exportação incompatível.
    assert any("measure_duration_mismatch" in issue for issue in score.issues())
    with pytest.raises(ValueError, match="incompleta"):
        to_musicxml(score)


def test_discontinuous_secondary_stroke_preserves_uncertainty():
    notes = _four_beamed()
    image = _page(notes[:2], beam_groups=((0, 1),))
    _draw_secondary(image, notes[0][:2], notes[1][:2], length=0.66)
    score = transcribe_one_measure(image, measure_left=110, measure_right=410, beats=1)
    events = score.parts[0].measures[0].notes
    assert len(events) == 2
    assert all(note.duration is None for note in events)
    assert "unknown_duration" in score.issues()


def test_thick_slanted_beam_does_not_fake_two_separated_stripes():
    notes = _four_beamed()[:2]
    image = _page(notes, beam_groups=((0, 1),))
    # Cobrir a região entre o primeiro traço e a suposta segunda faixa.
    _draw_secondary(image, notes[0][:2], notes[1][:2], thickness=22)
    result = detect_staffs(image)
    staff = result.staffs[0]
    heads = detect_noteheads(image, staff, result.threshold, 110, 410)
    stems = linked_stems(image, staff, result.threshold, heads)
    evidence = detect_rhythm_evidence(image, staff, result.threshold, heads, stems)
    assert not any(
        mark.kind == "double_beam" and mark.status == "accepted" for mark in evidence
    )


def test_barline_blocks_double_beam_across_measures():
    notes = _four_beamed()[:2]
    image = _page(notes, beam_groups=((0, 1),), double=True)
    result = detect_staffs(image)
    staff = result.staffs[0]
    heads = detect_noteheads(image, staff, result.threshold, 110, 410)
    stems = linked_stems(image, staff, result.threshold, heads)
    bar = BarlineCandidate(
        "manual-obstruction",
        180,
        Region(180, 74, 180, 138),
        1.0,
        "accepted",
        "test",
    )
    evidence = detect_rhythm_evidence(
        image, staff, result.threshold, heads, stems, barlines=(bar,)
    )
    assert not any(
        mark.kind == "double_beam" and mark.status == "accepted" for mark in evidence
    )


def _manual_four_sixteenths():
    notes = tuple(
        Note(
            Pitch("CDEG"[i], 5),
            Duration("sixteenth"),
            Region(10 + 20 * i, 40, 20 + 20 * i, 50),
            0,
            "filled",
            beam=("begin", "continue", "continue", "end")[i],
        )
        for i in range(4)
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


def test_sixteenth_note_is_exact_quarter_fraction_and_valid_two_level_musicxml():
    assert Duration("sixteenth").quarters == Fraction(1, 4)
    score = _manual_four_sixteenths()
    assert score.issues() == ()
    xml = ET.fromstring(to_musicxml(score))
    assert xml.findtext("./part/measure/attributes/divisions") == "4"
    notes = xml.findall("./part/measure/note")
    assert [(n.findtext("type"), n.findtext("duration")) for n in notes] == [
        ("16th", "1"),
    ] * 4
    for level in ("1", "2"):
        assert [n.find(f"beam[@number='{level}']").text for n in notes] == [
            "begin",
            "continue",
            "continue",
            "end",
        ]


def test_mixed_eighth_and_sixteenth_beamed_group_needs_partial_beam_model():
    original = _manual_four_sixteenths()
    part = original.parts[0]
    measure = part.measures[0]
    mixed = replace(
        measure,
        notes=(
            replace(measure.notes[0], duration=Duration("eighth")),
            *measure.notes[1:],
        ),
    )
    score = replace(original, parts=(replace(part, measures=(mixed,)),))
    assert any("mixed_beam_durations" in issue for issue in score.issues())
    with pytest.raises(ValueError, match="incompleta"):
        to_musicxml(score)


def test_unbeamed_sixteenth_is_valid_type_without_invented_beams():
    original = _manual_four_sixteenths()
    part = original.parts[0]
    measure = part.measures[0]
    ungrouped = replace(
        measure, notes=tuple(replace(note, beam=None) for note in measure.notes)
    )
    score = replace(original, parts=(replace(part, measures=(ungrouped,)),))
    assert score.issues() == ()
    xml = ET.fromstring(to_musicxml(score))
    assert len(xml.findall("./part/measure/note/beam")) == 0
