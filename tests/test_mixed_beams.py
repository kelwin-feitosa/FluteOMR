"""Feixes mistos obtidos de tinta, não do MusicXML nem das durações alvo."""

from xml.etree import ElementTree as ET

import pytest

from fluteomr.musicxml import to_musicxml
from fluteomr.transcription import transcribe_one_measure
from tests.test_eighths import _page
from tests.test_sixteenths import _draw_secondary


@pytest.mark.parametrize(
    ("pair", "kinds", "secondary"),
    [
        (
            (1, 2),
            ("eighth", "sixteenth", "sixteenth"),
            (None, "begin", "end"),
        ),
        (
            (0, 1),
            ("sixteenth", "sixteenth", "eighth"),
            ("begin", "end", None),
        ),
    ],
)
def test_mixed_beam_fixture_with_independent_engraving(pair, kinds, secondary):
    notes = (
        (145, 9, "eighth", "down"),
        (215, 8, "eighth", "down"),
        (285, 7, "eighth", "down"),
    )
    image = _page(notes, beam_groups=((0, 1, 2),))
    _draw_secondary(image, notes[pair[0]][:2], notes[pair[1]][:2])

    score = transcribe_one_measure(image, measure_left=110, measure_right=410, beats=1)
    assert score.issues() == ()
    events = score.parts[0].measures[0].notes
    assert len(events) == 3
    assert tuple(note.duration.kind for note in events) == kinds
    assert [note.beam for note in events] == ["begin", "continue", "end"]
    assert [
        dict(note.beam_levels).get(2) for note in events
    ] == list(secondary)
    assert all(
        "double_beam" in note.diagnostics
        if item == "sixteenth"
        else "beam" in note.diagnostics
        for note, item in zip(events, kinds, strict=True)
    )
    xml = ET.fromstring(to_musicxml(score))
    exported = xml.findall("./part/measure/note")
    assert [note.findtext("duration") for note in exported] == [
        "1" if item == "sixteenth" else "2" for item in kinds
    ]
    assert [
        (
            beam.text
            if (beam := note.find("beam[@number='2']")) is not None
            else None
        )
        for note in exported
    ] == list(secondary)


def test_weak_middle_second_beam_does_not_promote_unrelated_heads():
    notes = (
        (145, 9, "eighth", "down"),
        (215, 8, "eighth", "down"),
        (285, 7, "eighth", "down"),
        (355, 6, "eighth", "down"),
    )
    image = _page(notes, beam_groups=((0, 1, 2, 3),))
    _draw_secondary(image, notes[0][:2], notes[1][:2])
    # Dúvida sobre segundo feixe parcial entre as últimas duas hastes.
    _draw_secondary(image, notes[2][:2], notes[3][:2], length=0.53)
    score = transcribe_one_measure(image, measure_left=110, measure_right=410, beats=2)
    events = score.parts[0].measures[0].notes
    assert all(note.duration is None for note in events)
    assert all("double_beam" in note.diagnostics for note in events)
    with pytest.raises(ValueError, match="incompleta"):
        to_musicxml(score)
