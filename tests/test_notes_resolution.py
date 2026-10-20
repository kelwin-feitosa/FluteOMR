"""Regressões de rasterização em exercícios próprios, sem renderer no CI."""

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image, ImageDraw

from fluteomr.music_evaluation import evaluate_music
from fluteomr.notes import (
    NoteheadObservation,
    _deduplicate_candidates,
    _ink_without_staff,
    detect_noteheads,
)
from fluteomr.staff_detection import Region, Staff, StaffLine, detect_staffs
from fluteomr.transcription import transcribe_one_measure
from tools.music_examples import render_exercise

DATA = Path(__file__).parent / "data" / "music_lab"


@pytest.mark.parametrize("thickness", [1, 2, 3])
def test_staff_suppression_preserves_ink_outside_observed_band(thickness):
    image = Image.new("L", (60, 75), 255)
    draw = ImageDraw.Draw(image)
    lines = tuple(
        StaffLine(0, 59, 12 + i * 12 + (thickness - 1) / 2, thickness) for i in range(5)
    )
    for line in lines:
        draw.rectangle(
            (
                0,
                int(line.y - (thickness - 1) / 2),
                59,
                int(line.y + (thickness - 1) / 2),
            ),
            fill=0,
        )
    # Tinta de um símbolo junto à borda, sem continuidade vertical completa.
    draw.point((30, 11), fill=0)
    staff = Staff(lines, 12, Region(0, lines[0].y, 59, lines[-1].y))
    ink = _ink_without_staff(image, staff, 127)
    assert ink[11 * image.width + 30] == 1
    assert ink[12 * image.width + 10] == 0


@pytest.mark.parametrize("spacing", [10, 14, 21])
def test_duplicate_probes_prefer_attached_stem_without_changing_score(spacing):
    detached = NoteheadObservation(
        50, 50, Region(44, 46, 56, 54), "filled", False, 0.71, ("stem_not_confirmed",)
    )
    attached = replace(
        detached, center_x=52, stem_present=True, shape_score=0.70, diagnostics=()
    )
    distinct = replace(attached, center_x=round(52 + 2 * spacing))
    chosen = _deduplicate_candidates([detached, attached, distinct], spacing)
    assert chosen == (attached, distinct)
    assert chosen[0].shape_score == 0.70


@pytest.mark.parametrize("dpi,left,right", [(200, 20, 233), (300, 30, 350)])
def test_same_engraved_notes_match_independent_reference_at_both_resolutions(
    dpi, left, right
):
    with Image.open(DATA / "raster" / f"dev_down_flags-{dpi}.png") as image:
        score = transcribe_one_measure(image, measure_left=left, measure_right=right)
    report = evaluate_music((DATA / "dev_down_flags.musicxml").read_bytes(), score)
    assert report["matches"] == 4
    assert report["insertions"] == report["omissions"] == report["substitutions"] == 0
    assert score.issues() == ()


def test_normalized_heads_keep_original_coordinates_and_native_path():
    with Image.open(DATA / "raster" / "dev_down_flags-200.png") as image:
        detected = detect_staffs(image)
        staff = detected.staffs[0]
        native = detect_noteheads(image, staff, detected.threshold, 20, 233)
        normalized = detect_noteheads(
            image, staff, detected.threshold, 20, 233, normalize=True
        )
        assert len(native) == 3  # Baseline corrigida, sem resolver o anel quantizado.
        assert len(normalized) == 4
        expected = ((39, 79), (71, 86), (119, 72), (152, 93))
        for head, (x, y) in zip(normalized, expected, strict=True):
            assert abs(head.center_x - x) <= 2
            assert abs(head.center_y - y) <= 2
            assert head.region.left <= head.center_x <= head.region.right
            assert head.region.top <= head.center_y <= head.region.bottom
            assert head.stem_present
        # As sondas nativas válidas permanecem; só a cabeça recuperada é ampliada.
        assert "staff_space_normalized" in normalized[-1].diagnostics


@pytest.mark.parametrize("offset", [(31, 53), (100, 100)])
def test_normalized_geometry_is_invariant_to_page_margins(offset):
    with Image.open(DATA / "raster" / "dev_down_flags-200.png") as source:
        page = Image.new("RGB", (source.width + 200, source.height + 200), "white")
        page.paste(source, offset)
    score = transcribe_one_measure(
        page, measure_left=20 + offset[0], measure_right=233 + offset[0]
    )
    report = evaluate_music((DATA / "dev_down_flags.musicxml").read_bytes(), score)
    assert report["matches"] == 4
    assert score.issues() == ()


@pytest.mark.parametrize("factor", [2 / 3, 0.8, 1.0])
def test_filled_hollow_and_both_stem_directions_on_scaled_pillow_exercise(factor):
    image = render_exercise(((0, "quarter"), (5, "quarter"), (7, "half")))
    image = image.resize(
        tuple(round(v * factor) for v in image.size), Image.Resampling.LANCZOS
    )
    score = transcribe_one_measure(
        image, measure_left=round(110 * factor), measure_right=round(410 * factor)
    )
    notes = score.parts[0].measures[0].notes
    assert [(n.pitch.step, n.pitch.octave, n.duration.kind) for n in notes] == [
        ("E", 4, "quarter"),
        ("C", 5, "quarter"),
        ("E", 5, "half"),
    ]
    assert score.issues() == ()


def test_staff_crossing_beam_does_not_form_hollow_head():
    with Image.open(DATA / "raster" / "dev_eighth_beams-300.png") as image:
        score = transcribe_one_measure(image, measure_left=5, measure_right=310)
    report = evaluate_music((DATA / "dev_eighth_beams.musicxml").read_bytes(), score)
    assert report["matches"] == 5
    assert report["predicted_events"] == report["reference_events"] == 5
    assert report["insertions"] == report["omissions"] == 0
    assert score.issues() == ()


@pytest.mark.parametrize("factor", [2 / 3, 0.8])
def test_normalization_preserves_native_beamed_notes_at_smaller_scale(factor):
    with Image.open(DATA / "raster" / "dev_eighth_beams-300.png") as source:
        image = source.resize(
            tuple(round(v * factor) for v in source.size), Image.Resampling.LANCZOS
        )
    score = transcribe_one_measure(
        image, measure_left=round(5 * factor), measure_right=round(310 * factor)
    )
    report = evaluate_music((DATA / "dev_eighth_beams.musicxml").read_bytes(), score)
    assert report["matches"] == 5
    assert report["predicted_events"] == report["reference_events"] == 5
    assert score.issues() == ()


def test_cli_normalization_and_explicit_flute_keep_native_ablation(tmp_path):
    command = [
        sys.executable,
        "-m",
        "tools.transcribe",
        str(DATA / "raster" / "dev_down_flags-200.png"),
        "--clef",
        "treble",
        "--time",
        "4/4",
        "--measure-left",
        "20",
        "--measure-right",
        "233",
        "--instrument",
        "flute",
    ]
    automatic = tmp_path / "automatic.musicxml"
    completed = subprocess.run(
        [*command, "--output", str(automatic)], capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    root = ET.fromstring(automatic.read_bytes())
    assert len(root.findall("./part/measure/note")) == 4
    assert root.findtext("./part-list/score-part/midi-instrument/midi-program") == "74"
    native = tmp_path / "native.musicxml"
    completed = subprocess.run(
        [*command, "--native-heads", "--output", str(native)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "Transcrição incompleta" in completed.stderr
    assert not native.exists()
    assert len(json.loads(completed.stdout)["parts"][0]["measures"][0]["notes"]) == 3
