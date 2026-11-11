"""Guardas musicais: não atribuir precisão a símbolos que o OMR não conhece."""

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
from fluteomr.music_evaluation import evaluate_music, parse_reference
from fluteomr.staff_detection import Region


def _xml(measures):
    root = ET.Element("score-partwise")
    part = ET.SubElement(root, "part", id="P1")
    for index, notes in enumerate(measures, 1):
        measure = ET.SubElement(part, "measure", number=str(index))
        ET.SubElement(ET.SubElement(measure, "attributes"), "divisions").text = "2"
        for step, octave, duration, alteration in notes:
            note = ET.SubElement(measure, "note")
            pitch = ET.SubElement(note, "pitch")
            ET.SubElement(pitch, "step").text = step
            ET.SubElement(pitch, "octave").text = str(octave)
            if alteration is not None:
                ET.SubElement(pitch, "alter").text = str(alteration)
            ET.SubElement(note, "duration").text = str(duration)
    return ET.tostring(root)


def _score(measures):
    measure_objects = tuple(
        Measure(
            index,
            tuple(
                Note(
                    Pitch(step, octave),
                    Duration(duration),
                    Region(0, 0, 10, 10),
                    0,
                    "filled",
                )
                for step, octave, duration in notes
            ),
            TimeSignature(4, 4, "configuration"),
            "configuration",
        )
        for index, notes in enumerate(measures, 1)
    )
    return MusicScore(
        (
            MusicPart(
                "P1",
                "Flauta",
                "configuration",
                (0,),
                Clef("treble", "configuration"),
                measure_objects,
            ),
        )
    )


def _notation_xml(measures, *, key=None, time=None, clef=None, reset_key=None):
    root = ET.fromstring(_xml(measures))
    for index, measure in enumerate(root.findall("part/measure")):
        attributes = measure.find("attributes")
        if index == 0:
            if key is not None:
                ET.SubElement(ET.SubElement(attributes, "key"), "fifths").text = str(
                    key
                )
            if time is not None:
                signature = ET.SubElement(attributes, "time")
                ET.SubElement(signature, "beats").text = str(time[0])
                ET.SubElement(signature, "beat-type").text = str(time[1])
            if clef is not None:
                sign = ET.SubElement(attributes, "clef")
                ET.SubElement(sign, "sign").text = clef[0]
                ET.SubElement(sign, "line").text = str(clef[1])
        if reset_key is not None and index == len(measures) - 1:
            ET.SubElement(ET.SubElement(attributes, "key"), "fifths").text = str(
                reset_key
            )
    return ET.tostring(root)


def test_nonzero_key_cannot_be_scored_as_natural_pitch_even_without_alter():
    xml = _notation_xml([[("F", 4, 2, None)]], key=1)
    result = evaluate_music(xml, _score([[("F", 4, "quarter")]]))
    assert result["status"] == "partial"
    assert result["unsupported"]["key_signature"] == 1
    assert result["matches"] == 0
    assert result["skipped_reference_events"] == 1
    assert result["measure_results"][0]["status"] == "unevaluable"


def test_key_signature_persists_between_measures_and_can_reset():
    xml = _notation_xml(
        [
            [("F", 4, 2, None)],
            [("F", 4, 2, None)],
            [("F", 4, 2, None)],
        ],
        key=-1,
        reset_key=0,
    )
    reference = parse_reference(xml)[0]
    assert [measure.unsupported for measure in reference] == [
        "key_signature",
        "key_signature",
        None,
    ]
    evaluated = evaluate_music(xml, _score([[("F", 4, "quarter")]] * 3))
    assert evaluated["matches"] == 1
    assert evaluated["skipped_reference_events"] == 2


def test_nonstandard_key_does_not_silently_become_c_major():
    xml = _notation_xml([[("E", 4, 2, None)]])
    root = ET.fromstring(xml)
    key = ET.SubElement(root.find("part/measure/attributes"), "key")
    ET.SubElement(key, "key-step").text = "E"
    result = parse_reference(ET.tostring(root))
    assert result[0][0].unsupported == "nontraditional_key"


@pytest.mark.parametrize(
    ("time", "clef", "reason"),
    [
        ((3, 4), None, "time_signature"),
        (None, ("F", 4), "clef"),
    ],
)
def test_unsupported_meter_or_clef_is_not_a_perfect_measure(time, clef, reason):
    xml = _notation_xml([[("E", 4, 2, None)]], time=time, clef=clef)
    result = evaluate_music(xml, _score([[("E", 4, "quarter")]]))
    assert result["status"] == "partial"
    assert result["matches"] == 0
    assert result["unsupported"][reason] == 1


def test_invalid_fifths_is_rejected_not_ignored():
    xml = _notation_xml([[("F", 4, 2, None)]], key="oops")
    with pytest.raises(ValueError):
        parse_reference(xml)
