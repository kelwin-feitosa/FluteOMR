"""Erros conhecidos em referências MusicXML escritas independentemente do OMR."""

import json
from dataclasses import replace
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
from fluteomr.music_evaluation import evaluate_music
from fluteomr.notes import NoteheadObservation, _deduplicate_candidates
from fluteomr.staff_detection import Region
from tools.evaluate_music import evaluate_manifest
from tools.music_examples import EXERCISES, render_exercise


def _xml(measures, divisions=2):
    root = ET.Element("score-partwise")
    part = ET.SubElement(root, "part", id="P1")
    for number, events in enumerate(measures, 1):
        measure = ET.SubElement(part, "measure", number=str(number))
        attrs = ET.SubElement(measure, "attributes")
        ET.SubElement(attrs, "divisions").text = str(divisions)
        for step, octave, ticks, alter in events:
            note = ET.SubElement(measure, "note")
            if step is None:
                ET.SubElement(note, "rest")
            else:
                pitch = ET.SubElement(note, "pitch")
                ET.SubElement(pitch, "step").text = step
                ET.SubElement(pitch, "octave").text = str(octave)
                if alter is not None:
                    ET.SubElement(pitch, "alter").text = str(alter)
            ET.SubElement(note, "duration").text = str(ticks)
    return ET.tostring(root)


def _score(measures):
    region = Region(0, 0, 10, 10)
    built = tuple(
        Measure(
            number,
            tuple(
                Note(Pitch(step, octave), Duration(kind), region, 0, "filled")
                for step, octave, kind in events
            ),
            TimeSignature(4, 4, "configuration"),
            "configuration",
        )
        for number, events in enumerate(measures, 1)
    )
    return MusicScore(
        (MusicPart("P1", "x", "unknown", (0,), Clef("treble", "configuration"), built),)
    )


BASE = _xml([[("E", 4, 2, None), ("F", 4, 4, None)]])


@pytest.mark.parametrize(
    ("prediction", "field", "expected"),
    [
        ([[("E", 4, "quarter"), ("F", 4, "half")]], "matches", 2),
        ([[("G", 4, "quarter"), ("F", 4, "half")]], "pitch_errors", 1),
        ([[("E", 5, "quarter"), ("F", 4, "half")]], "octave_errors", 1),
        ([[("E", 4, "half"), ("F", 4, "half")]], "duration_errors", 1),
        ([[("E", 4, "quarter")]], "omissions", 1),
        (
            [[("E", 4, "quarter"), ("F", 4, "half"), ("G", 4, "quarter")]],
            "insertions",
            1,
        ),
        ([[("F", 4, "half"), ("E", 4, "quarter")]], "substitutions", 2),
    ],
)
def test_musical_alignment_known_errors(prediction, field, expected):
    report = evaluate_music(BASE, _score(prediction))
    assert report[field] == expected
    assert report["reference_xml_parsed"] is True
    assert report["notation_graphics"] == "not_evaluated"


def test_measure_omission_and_insertion_are_explicit():
    reference = _xml([[("E", 4, 2, None)], [("F", 4, 2, None)]])
    missing = evaluate_music(reference, _score([[("E", 4, "quarter")]]))
    assert missing["measure_errors"]["omissions"] == 1
    assert missing["omissions"] == 1
    extra = evaluate_music(
        BASE, _score([[("E", 4, "quarter"), ("F", 4, "half")], [("G", 4, "quarter")]])
    )
    assert extra["measure_errors"]["insertions"] == 1
    assert extra["insertions"] == 1


def test_missing_middle_measure_does_not_shift_later_comparison():
    reference = _xml([[("E", 4, 2, None)], [("F", 4, 2, None)], [("G", 4, 2, None)]])
    score = _score([[("E", 4, "quarter")], [("G", 4, "quarter")]])
    part = score.parts[0]
    third = replace(part.measures[1], number=3)
    score = replace(score, parts=(replace(part, measures=(part.measures[0], third)),))
    report = evaluate_music(reference, score)
    assert report["matches"] == 2
    assert report["measure_errors"]["omissions"] == 1
    assert report["omissions"] == 1
    assert report["substitutions"] == 0


def test_unsupported_rest_and_alter_do_not_count_as_correct():
    rest = _xml([[("E", 4, 2, None), (None, None, 2, None)]])
    altered = _xml([[("F", 4, 2, 1)]])
    for xml, reason in ((rest, "rest"), (altered, "chromatic_alteration")):
        report = evaluate_music(xml, _score([[("E", 4, "quarter")]]))
        assert report["status"] == "partial"
        assert report["unsupported"][reason] == 1
        assert report["matches"] == 0


def test_fractional_duration_and_invalid_xml():
    reference = _xml([[("E", 4, 1, None)]], divisions=2)
    report = evaluate_music(reference, _score([[("E", 4, "quarter")]]))
    assert report["duration_errors"] == 1
    with pytest.raises(ET.ParseError):
        evaluate_music(b"<broken", _score([[("E", 4, "quarter")]]))


def test_alignment_reports_full_pitch_duration_and_coverage_separately():
    reference = _xml([[("E", 4, 2, None), ("F", 4, 1, None)]])
    score = _score([[("E", 5, "quarter"), ("F", 4, "quarter")]])
    report = evaluate_music(reference, score)
    assert report["matches"] == 0
    assert report["aligned_events"] == 2
    assert report["pitch_correct_aligned"] == 1
    assert report["duration_correct_aligned"] == 1
    assert report["full_match_fraction"] == {"matched": 0, "expected": 2}
    assert report["duration_coverage"] == {"resolved": 2, "total": 2}


def test_inconclusive_measure_is_explicitly_unscored():
    reference = _xml([[("E", 4, 2, None), ("F", 4, 1, None)]])
    score = _score([[("E", 4, "quarter"), ("F", 4, "quarter")]])
    part = score.parts[0]
    measure = part.measures[0]
    unknown = replace(measure.notes[1], duration=None, duration_origin="unknown")
    measure = replace(measure, notes=(measure.notes[0], unknown))
    score = replace(score, parts=(replace(part, measures=(measure,)),))
    report = evaluate_music(reference, score)
    assert report["status"] == "partial"
    assert report["inconclusive_predicted_events"] == 1
    assert report["skipped_reference_events"] == 2
    assert report["skipped_predicted_events"] == 2
    assert report["full_match_fraction"] == "not_evaluated"
    assert report["duration_coverage"] == {"resolved": 1, "total": 2}


def test_lab_transcribes_before_reading_source_authored_reference(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    render_exercise(EXERCISES["dev_lines_spaces"][1]).save(images / "example.png")
    reference = tmp_path / "reference.musicxml"
    reference.write_bytes(
        _xml([[("E", 4, 2, None), ("F", 4, 2, None), ("G", 4, 4, None)]])
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format_version": 1,
                "examples": [
                    {
                        "id": "original",
                        "image": "example.png",
                        "reference": reference.name,
                        "origin": "original_programmatic_exercise",
                        "split": "development",
                        "reference_status": "source_authored",
                        "configured": {"measure_left": 110, "measure_right": 410},
                    }
                ],
            }
        )
    )
    row = evaluate_manifest(manifest, images)[0]
    assert row["evaluation"]["matches"] == 3
    assert row["evaluation"]["reference_events"] == 3
    assert row["evaluation"]["predicted_events"] == 3
    assert row["evaluation"]["insertions"] == row["evaluation"]["omissions"] == 0
    assert row["xml_export"] == "well_formed_not_schema_validated"
    manifest.write_text(manifest.read_text().replace("source_authored", "draft"))
    assert evaluate_manifest(manifest, images)[0]["evaluation"] == "not_evaluated"


def _candidate(x, y, spacing, score=0.9):
    rx = round(0.65 * spacing)
    ry = round(0.42 * spacing)
    return NoteheadObservation(
        x, y, Region(x - rx, y - ry, x + rx, y + ry), "filled", True, score, ()
    )


@pytest.mark.parametrize("spacing", (8, 16, 24))
def test_duplicate_probes_merge_but_adjacent_degrees_survive(spacing):
    first = _candidate(100, 100, spacing)
    duplicate = _candidate(101, 100 + round(0.5 * spacing), spacing, 0.5)
    next_note = _candidate(100 + round(0.8 * spacing), 100 + spacing, spacing)
    chosen = _deduplicate_candidates([first, duplicate, next_note], spacing)
    assert {(h.center_x, h.center_y) for h in chosen} == {
        (first.center_x, first.center_y),
        (next_note.center_x, next_note.center_y),
    }


@pytest.mark.parametrize("spacing", (8, 16, 24))
def test_staff_line_space_and_ink_fragment_do_not_create_extra_head(spacing):
    line = _candidate(100, 100, spacing)
    space = _candidate(100 + 2 * spacing, 100 - round(spacing / 2), spacing)
    fragment = NoteheadObservation(
        101, 100, line.region, "hollow", False, 0.1, ("stem_not_confirmed",)
    )
    chosen = _deduplicate_candidates([fragment, space, line], spacing)
    assert chosen == (line, space)
