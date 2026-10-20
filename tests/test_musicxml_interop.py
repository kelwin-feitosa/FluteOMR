"""Contratos de intercâmbio independentes do reconhecimento de pixels."""

from dataclasses import replace
from fractions import Fraction
from xml.etree import ElementTree as ET

import pytest

from fluteomr.music import (
    Clef,
    Duration,
    Instrument,
    Measure,
    MusicPart,
    MusicScore,
    Note,
    Pitch,
    TimeSignature,
)
from fluteomr.musicxml import to_musicxml
from fluteomr.staff_detection import Region


def _score(*, beams=("begin", "end", None, None), instrument=None):
    # Referência escrita manualmente: C5/8, D5/8, E5/4, F5/2 = 4 tempos.
    notes = tuple(
        Note(
            Pitch(step, 5),
            Duration(kind),
            Region(10, 20, 30, 40),
            0,
            "hollow" if kind == "half" else "filled",
            beam=beam,
        )
        for (step, kind), beam in zip(
            (("C", "eighth"), ("D", "eighth"), ("E", "quarter"), ("F", "half")),
            beams,
            strict=True,
        )
    )
    return MusicScore(
        (
            MusicPart(
                "P1",
                "Parte informada",
                "user",
                (0,),
                Clef("treble", "configuration"),
                (
                    Measure(
                        1, notes, TimeSignature(4, 4, "configuration"), "configuration"
                    ),
                ),
                instrument=instrument,
            ),
        )
    )


def test_explicit_flute_identity_preserves_music_and_user_part_name():
    score = _score(instrument=Instrument.flute(origin="user"))
    root = ET.fromstring(to_musicxml(score))
    listed = root.find("./part-list/score-part")
    assert listed.findtext("part-name") == "Parte informada"
    assert listed.findtext("score-instrument/instrument-name") == "Flute"
    assert listed.findtext("score-instrument/instrument-sound") == "wind.flutes.flute"
    assert listed.findtext("midi-instrument/midi-program") == "74"
    assert (
        listed.find("score-instrument").attrib["id"]
        == listed.find("midi-instrument").attrib["id"]
    )
    assert score.to_dict()["parts"][0]["instrument"]["origin"] == "user"
    notes = root.findall("./part/measure/note")
    divisions = int(root.findtext("./part/measure/attributes/divisions"))
    assert [
        (
            note.findtext("pitch/step"),
            int(note.findtext("pitch/octave")),
            Fraction(note.findtext("duration")) / divisions,
            note.findtext("beam"),
        )
        for note in notes
    ] == [
        ("C", 5, Fraction(1, 2), "begin"),
        ("D", 5, Fraction(1, 2), "end"),
        ("E", 5, Fraction(1), None),
        ("F", 5, Fraction(2), None),
    ]


def test_no_instrument_is_guessed_from_part_name():
    score = _score()
    score = replace(score, parts=(replace(score.parts[0], name="Flute"),))
    root = ET.fromstring(to_musicxml(score))
    assert root.find("./part-list/score-part/score-instrument") is None
    assert root.find("./part-list/score-part/midi-instrument") is None
    assert score.parts[0].instrument is None


@pytest.mark.parametrize("program", [0, 129, 73.5, True])
def test_invalid_midi_program_rejected(program):
    with pytest.raises(ValueError, match="MIDI"):
        Instrument("Flute", midi_program=program)


@pytest.mark.parametrize(
    "beams, issue",
    [
        (("end", None, None, None), "beam_without_begin"),
        (("begin", None, None, None), "beam_interrupted"),
        (("begin", "continue", None, None), "beam_interrupted"),
        (("begin", "begin", None, None), "beam_restarted"),
        (("begin", "end", "begin", None), "beam_requires_eighth"),
        ((None, None, None, "begin"), "beam_without_end"),
    ],
)
def test_export_rejects_malformed_beam_relations(beams, issue):
    score = _score(beams=beams)
    assert any(problem.startswith(issue) for problem in score.issues())
    with pytest.raises(ValueError, match=issue):
        to_musicxml(score)


def test_unbeamed_eighths_remain_unbeamed():
    root = ET.fromstring(to_musicxml(_score(beams=(None,) * 4)))
    assert root.findall("./part/measure/note/beam") == []


def test_flute_does_not_restrict_written_register_or_transpose():
    score = _score(instrument=Instrument.flute())
    part = score.parts[0]
    measure = part.measures[0]
    notes = (replace(measure.notes[0], pitch=Pitch("C", 3)), *measure.notes[1:])
    score = replace(
        score, parts=(replace(part, measures=(replace(measure, notes=notes),)),)
    )
    root = ET.fromstring(to_musicxml(score))
    assert root.findtext("./part/measure/note/pitch/octave") == "3"
    assert root.find(".//transpose") is None
