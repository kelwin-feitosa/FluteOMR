"""Métricas controladas de um compasso; a referência não entra na inferência."""

import json
import subprocess
import sys
from xml.etree import ElementTree as ET

import pytest
from PIL import Image, ImageDraw

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
from fluteomr.notes import detect_noteheads, pitch_from_y
from fluteomr.staff_detection import Region, Staff, StaffLine, detect_staffs
from fluteomr.symbols import detect_barlines
from fluteomr.transcription import transcribe_measures, transcribe_one_measure
from tools.music_examples import EXERCISES, MEASURE_LEFT, MEASURE_RIGHT, render_exercise


def _staff(spacing=16):
    return Staff(
        tuple(
            StaffLine(25, 455, 138 - index * spacing, 2) for index in range(4, -1, -1)
        ),
        spacing,
        Region(25, 138 - 4 * spacing, 455, 138),
    )


@pytest.mark.parametrize(
    ("degree", "expected"),
    list(
        enumerate(
            (
                "A3",
                "B3",
                "C4",
                "D4",
                "E4",
                "F4",
                "G4",
                "A4",
                "B4",
                "C5",
                "D5",
                "E5",
                "F5",
                "G5",
                "A5",
                "B5",
                "C6",
            ),
            start=-4,
        )
    ),
)
def test_treble_pitch_on_lines_spaces_and_ledgers(degree, expected):
    for spacing in (12, 16, 20):
        staff = _staff(spacing)
        pitch = pitch_from_y(138 - degree * spacing / 2, staff)
        assert f"{pitch.step}{pitch.octave}" == expected
    assert pitch_from_y(138 - degree * 16 / 2 + 3, _staff()) is None


def test_model_rejects_missing_information_and_unbalanced_measure():
    region = Region(10, 20, 30, 40)
    known = Note(Pitch("E", 4), Duration("quarter"), region, 0, "filled")
    measure = Measure(
        1, (known,), TimeSignature(4, 4, "configuration"), "configuration"
    )
    score = MusicScore(
        (
            MusicPart(
                "P1",
                "Parte 1",
                "unknown",
                (0,),
                Clef("treble", "configuration"),
                (measure,),
            ),
        )
    )
    assert measure.issues() == ("measure_duration_mismatch:1/4",)
    with pytest.raises(ValueError, match="incompleta"):
        to_musicxml(score)
    unknown = Note(
        Pitch("E", 4),
        None,
        region,
        0,
        "filled",
        ("stem_not_confirmed",),
        duration_origin="unknown",
    )
    incomplete = Measure(
        1, (unknown,), TimeSignature(4, 4, "configuration"), "configuration"
    )
    assert incomplete.issues() == ("unknown_duration",)
    with pytest.raises(ValueError, match="unknown_duration"):
        to_musicxml(
            MusicScore(
                (
                    MusicPart(
                        "P1",
                        "Parte 1",
                        "unknown",
                        (0,),
                        Clef("treble", "configuration"),
                        (incomplete,),
                    ),
                )
            )
        )


def test_notehead_negative_symbols_and_unconfirmed_stem():
    image = Image.new("RGB", (480, 215), "white")
    draw = ImageDraw.Draw(image)
    for index in range(5):
        y = 138 - index * 16
        draw.line((25, y, 455, y), fill="black", width=2)
    draw.line((220, 74, 220, 138), fill="black", width=2)
    draw.ellipse((65, 115, 85, 129), fill="black")  # fora do compasso
    result = detect_staffs(image)
    assert result.staff_count == 1
    assert detect_noteheads(image, result.staffs[0], result.threshold, 110, 410) == ()
    draw.ellipse((290, 115, 310, 129), fill="black")  # sem haste
    result = detect_staffs(image)
    heads = detect_noteheads(image, result.staffs[0], result.threshold, 110, 410)
    assert len(heads) == 1
    assert heads[0].visual_kind == "filled"
    assert not heads[0].stem_present
    score = transcribe_one_measure(image, measure_left=110, measure_right=410)
    assert score.parts[0].measures[0].notes[0].duration is None
    assert "unknown_duration" in score.issues()


@pytest.mark.parametrize("name", ("dev_lines_spaces", "dev_stems", "dev_ledger"))
def test_end_to_end_development_exercises(name):
    _, reference = EXERCISES[name]
    image = render_exercise(reference)
    score = transcribe_one_measure(
        image, measure_left=MEASURE_LEFT, measure_right=MEASURE_RIGHT
    )
    notes = score.parts[0].measures[0].notes
    expected = [
        (pitch_from_y(138 - degree * 8, _staff()), duration)
        for degree, duration in reference
    ]
    assert len(notes) == len(expected)
    assert [(note.pitch, note.duration.kind) for note in notes] == expected
    assert all(note.status == "recognized" for note in notes)
    assert all(note.pitch_origin == note.duration_origin == "image" for note in notes)
    assert score.parts[0].clef.origin == "configuration"
    assert score.parts[0].measures[0].time_signature.origin == "configuration"
    assert score.issues() == ()
    root = ET.fromstring(to_musicxml(score))
    xml_notes = root.findall("./part/measure/note")
    assert [
        n.findtext("pitch/step") + n.findtext("pitch/octave") for n in xml_notes
    ] == [f"{pitch.step}{pitch.octave}" for pitch, _ in expected]
    assert [n.findtext("type") for n in xml_notes] == [
        duration for _, duration in expected
    ]
    assert [n.findtext("duration") for n in xml_notes] == [
        "1" if duration == "quarter" else "2" for _, duration in expected
    ]


def test_transcription_rejects_multiple_staffs():
    image = render_exercise(EXERCISES["dev_lines_spaces"][1])
    draw = ImageDraw.Draw(image)
    for index in range(5):
        draw.line((25, 160 + index * 10, 455, 160 + index * 10), fill="black")
    with pytest.raises(ValueError, match="uma pauta"):
        transcribe_one_measure(image, measure_left=110, measure_right=410)


def test_experimental_cli_writes_inferred_xml_without_overwriting(tmp_path):
    image_path = tmp_path / "exercise.png"
    output = tmp_path / "exercise.musicxml"
    render_exercise(EXERCISES["dev_lines_spaces"][1]).save(image_path)
    command = [
        sys.executable,
        "-m",
        "tools.transcribe",
        str(image_path),
        "--clef",
        "treble",
        "--time",
        "4/4",
        "--measure-left",
        "110",
        "--measure-right",
        "410",
        "--output",
        str(output),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["issues"] == []
    assert [
        n.findtext("pitch/step")
        for n in ET.parse(output).findall("./part/measure/note")
    ] == ["E", "F", "G"]
    original = output.read_bytes()
    repeated = subprocess.run(command, capture_output=True, text=True, check=False)
    assert repeated.returncode != 0
    assert output.read_bytes() == original


def _two_measure_image():
    image = Image.new("RGB", (760, 215), "white")
    draw = ImageDraw.Draw(image)
    for y in (74, 90, 106, 122, 138):
        draw.line((25, y, 735, y), fill="black", width=2)
    draw.line((380, 74, 380, 138), fill="black", width=2)
    for x, degree, kind in (
        (140, 0, "quarter"),
        (210, 1, "quarter"),
        (280, 2, "half"),
        (460, 3, "quarter"),
        (530, 4, "quarter"),
        (625, 5, "half"),
    ):
        y = 138 - degree * 8
        box = (x - 10, y - 7, x + 10, y + 7)
        if kind == "quarter":
            draw.ellipse(box, fill="black")
        else:
            draw.ellipse(box, fill="white", outline="black", width=2)
        stem_x = x + 9 if degree <= 4 else x - 9
        stem_end = y - 54 if degree <= 4 else y + 54
        draw.line((stem_x, y, stem_x, stem_end), fill="black", width=2)
    return image


def test_internal_barline_separates_two_inferred_measures():
    image = _two_measure_image()
    result = transcribe_measures(image, content_left=100, content_right=700)
    assert [
        (bar.x, bar.status) for bar in result.barlines if bar.status == "accepted"
    ] == [(380, "accepted")]
    assert len(result.stems) == 6
    assert result.score.issues() == ()
    measures = result.score.parts[0].measures
    assert len(measures) == 2
    assert [[note.pitch.step for note in measure.notes] for measure in measures] == [
        ["E", "F", "G"],
        ["A", "B", "C"],
    ]
    assert [[note.duration.kind for note in measure.notes] for measure in measures] == [
        ["quarter", "quarter", "half"],
        ["quarter", "quarter", "half"],
    ]
    assert all(note.candidate_id for measure in measures for note in measure.notes)
    assert all(note.source_page == 1 for measure in measures for note in measure.notes)
    assert all(measure.source_region for measure in measures)
    assert [measure.boundary_origins for measure in measures] == [
        ("configuration", "image"),
        ("image", "configuration"),
    ]
    xml = ET.fromstring(to_musicxml(result.score))
    assert len(xml.findall("./part/measure")) == 2
    assert [len(m.findall("note")) for m in xml.findall("./part/measure")] == [3, 3]


def test_stems_are_not_barlines_and_missing_bar_is_rejected():
    image = _two_measure_image()
    draw = ImageDraw.Draw(image)
    draw.rectangle((378, 73, 383, 139), fill="white")
    result = detect_staffs(image)
    assert result.staff_count == 1
    heads = detect_noteheads(image, result.staffs[0], result.threshold, 100, 700)
    bars = detect_barlines(image, result.staffs[0], result.threshold, 100, 700, heads)
    assert all(bar.status != "accepted" for bar in bars)
    with pytest.raises(ValueError, match="nenhuma barra"):
        transcribe_measures(image, content_left=100, content_right=700)


def test_vertical_ink_joining_a_head_is_rejected_as_bar():
    image = _two_measure_image()
    draw = ImageDraw.Draw(image)
    draw.line((140, 74, 140, 138), fill="black", width=2)
    result = transcribe_measures(image, content_left=100, content_right=700)
    assert [bar.x for bar in result.barlines if bar.status == "accepted"] == [380]
    assert any(bar.evidence == "near_notehead" for bar in result.barlines)


def test_multimeasure_cli_writes_xml_and_debug_without_changing_image(tmp_path):
    image_path = tmp_path / "two.png"
    output = tmp_path / "two.musicxml"
    debug = tmp_path / "two-debug.png"
    _two_measure_image().save(image_path)
    before = image_path.read_bytes()
    command = [
        sys.executable,
        "-m",
        "tools.transcribe",
        str(image_path),
        "--clef",
        "treble",
        "--time",
        "4/4",
        "--measure-left",
        "100",
        "--measure-right",
        "700",
        "--auto-bars",
        "--debug",
        str(debug),
        "--output",
        str(output),
    ]
    run = subprocess.run(command, capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert len(report["parts"][0]["measures"]) == 2
    assert [
        bar["x"]
        for bar in report["symbol_diagnostics"]["barlines"]
        if bar["status"] == "accepted"
    ] == [380]
    assert any(
        bar["evidence"] == "near_notehead"
        for bar in report["symbol_diagnostics"]["barlines"]
    )
    assert len(ET.parse(output).findall("./part/measure")) == 2
    assert debug.exists() and image_path.read_bytes() == before
