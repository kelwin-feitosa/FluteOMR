"""Colcheias: referências musicais explícitas e desenhos independentes do detector."""

from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image, ImageDraw

from fluteomr.music_evaluation import evaluate_music
from fluteomr.musicxml import to_musicxml
from fluteomr.notes import detect_noteheads
from fluteomr.rhythm import detect_rhythm_evidence
from fluteomr.staff_detection import Region, detect_staffs
from fluteomr.symbols import BarlineCandidate, linked_stems
from fluteomr.transcription import transcribe_measures, transcribe_one_measure

REFERENCES = Path(__file__).parent / "data" / "music_lab"


def _page(notes, *, spacing=16, beam_groups=(), double=False, down_flag_right=False):
    """Desenha pautas e figuras por primitivas Pillow; não consulta o MusicXML."""
    width, height, bottom = 480, 215, 138
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for line in range(5):
        y = bottom - line * spacing
        draw.line((25, y, 455, y), fill="black", width=2)
    tips = {}
    rx, ry = round(0.65 * spacing), round(0.42 * spacing)
    for index, (x, degree, kind, direction) in enumerate(notes):
        y = bottom - round(degree * spacing / 2)
        head = (x - rx, y - ry, x + rx, y + ry)
        if kind == "half":
            draw.ellipse(head, fill="white", outline="black", width=2)
        else:
            draw.ellipse(head, fill="black")
        stem_x = x + (rx - 1 if direction == "up" else -rx + 1)
        tip_y = y + (
            -round(3.3 * spacing) if direction == "up" else round(3.3 * spacing)
        )
        draw.line((stem_x, y, stem_x, tip_y), fill="black", width=2)
        tips[index] = (stem_x, tip_y)
    beamed = {index for group in beam_groups for index in group}
    for group in beam_groups:
        for first, second in zip(group, group[1:], strict=False):
            draw.line((*tips[first], *tips[second]), fill="black", width=5)
            if double:
                offset = 13 if notes[first][3] == "up" else -13
                draw.line(
                    (
                        tips[first][0],
                        tips[first][1] + offset,
                        tips[second][0],
                        tips[second][1] + offset,
                    ),
                    fill="black",
                    width=4,
                )
    for index, (_, _, kind, direction) in enumerate(notes):
        if kind != "eighth" or index in beamed:
            continue
        x, y = tips[index]
        side = 1 if direction == "up" or down_flag_right else -1
        down = 1 if direction == "up" else -1
        draw.line(
            (
                x,
                y,
                x + side * round(0.6 * spacing),
                y + down * round(0.55 * spacing),
                x + side * round(0.8 * spacing),
                y + down * round(1.1 * spacing),
            ),
            fill="black",
            width=4,
            joint="curve",
        )
    return image


def _score(image):
    return transcribe_one_measure(image, measure_left=110, measure_right=410)


def test_eighth_fraction_and_musicxml_beam():
    image = _page(
        (
            (145, 9, "eighth", "down"),
            (195, 8, "eighth", "down"),
            (245, 7, "eighth", "down"),
            (295, 6, "eighth", "down"),
            (355, 4, "half", "up"),
        ),
        beam_groups=((0, 1, 2, 3),),
    )
    score = _score(image)
    notes = score.parts[0].measures[0].notes
    assert len(notes) == 5
    assert [note.duration.quarters for note in notes] == [Fraction(1, 2)] * 4 + [
        Fraction(2)
    ]
    assert [note.beam for note in notes] == [
        "begin",
        "continue",
        "continue",
        "end",
        None,
    ]
    xml = ET.fromstring(to_musicxml(score))
    assert xml.findtext("./part/measure/attributes/divisions") == "2"
    assert [n.findtext("duration") for n in xml.findall("./part/measure/note")] == [
        "1",
        "1",
        "1",
        "1",
        "4",
    ]
    assert [n.findtext("beam") for n in xml.findall("./part/measure/note")] == [
        "begin",
        "continue",
        "continue",
        "end",
        None,
    ]


def test_two_isolated_flags_and_old_durations():
    image = _page(
        (
            (145, 2, "eighth", "up"),
            (215, 4, "quarter", "up"),
            (285, 3, "eighth", "up"),
            (355, 5, "half", "down"),
        )
    )
    score = _score(image)
    assert [note.duration.kind for note in score.parts[0].measures[0].notes] == [
        "eighth",
        "quarter",
        "eighth",
        "half",
    ]
    assert all(note.beam is None for note in score.parts[0].measures[0].notes)
    assert score.issues() == ()


def test_downward_flag_without_beam():
    image = _page(
        (
            (145, 9, "eighth", "down"),
            (215, 7, "quarter", "down"),
            (285, 8, "eighth", "down"),
            (355, 4, "half", "up"),
        )
    )
    score = _score(image)
    assert [note.duration.kind for note in score.parts[0].measures[0].notes] == [
        "eighth",
        "quarter",
        "eighth",
        "half",
    ]


def test_downward_flag_curving_right_like_music_engraving():
    image = _page(
        (
            (145, 9, "eighth", "down"),
            (215, 7, "quarter", "down"),
            (285, 8, "eighth", "down"),
            (355, 4, "half", "up"),
        ),
        down_flag_right=True,
    )
    score = _score(image)
    assert [note.duration.kind for note in score.parts[0].measures[0].notes] == [
        "eighth",
        "quarter",
        "eighth",
        "half",
    ]


def test_long_beam_uses_ink_continuity_not_note_distance():
    image = _page(
        ((145, 8, "eighth", "down"), (360, 6, "eighth", "down")),
        beam_groups=((0, 1),),
    )
    detected = detect_staffs(image)
    staff = detected.staffs[0]
    heads = detect_noteheads(image, staff, detected.threshold, 110, 410)
    stems = linked_stems(image, staff, detected.threshold, heads)
    marks = detect_rhythm_evidence(image, staff, detected.threshold, heads, stems)
    assert [(mark.kind, mark.beam_position) for mark in marks] == [
        ("beam", "begin"),
        ("beam", "end"),
    ]


@pytest.mark.parametrize(("direction", "degrees"), [("down", (6, 8)), ("up", (2, 4))])
def test_long_beam_with_opposite_slope_and_stem_direction(direction, degrees):
    image = _page(
        (
            (145, degrees[0], "eighth", direction),
            (360, degrees[1], "eighth", direction),
        ),
        beam_groups=((0, 1),),
    )
    detected = detect_staffs(image)
    staff = detected.staffs[0]
    heads = detect_noteheads(image, staff, detected.threshold, 110, 410)
    stems = linked_stems(image, staff, detected.threshold, heads)
    marks = detect_rhythm_evidence(image, staff, detected.threshold, heads, stems)
    assert [(mark.kind, mark.beam_position) for mark in marks] == [
        ("beam", "begin"),
        ("beam", "end"),
    ]


@pytest.mark.parametrize("spacing", [12, 16, 20])
def test_downward_flag_scales_with_staff_spacing(spacing):
    image = _page(
        ((145, 8, "eighth", "down"), (215, 6, "quarter", "down")),
        spacing=spacing,
        down_flag_right=True,
    )
    score = _score(image)
    assert [note.duration.kind for note in score.parts[0].measures[0].notes] == [
        "eighth",
        "quarter",
    ]


def test_short_horizontal_mark_at_stem_tip_is_not_a_flag():
    image = _page(((145, 8, "quarter", "down"), (215, 6, "quarter", "down")))
    ImageDraw.Draw(image).line((136, 129, 149, 129), fill="black", width=3)
    score = _score(image)
    assert [note.duration.kind for note in score.parts[0].measures[0].notes] == [
        "quarter",
        "quarter",
    ]


def test_partial_curved_mark_keeps_duration_unknown_and_blocks_export():
    image = _page(((145, 8, "quarter", "down"), (215, 6, "quarter", "down")))
    ImageDraw.Draw(image).line((136, 129, 139, 124, 143, 117), fill="black", width=3)
    score = _score(image)
    first = score.parts[0].measures[0].notes[0]
    assert first.pitch is not None
    assert first.duration is None
    assert "weak_flag_geometry" in first.diagnostics
    with pytest.raises(ValueError, match="incompleta"):
        to_musicxml(score)


def test_near_complete_but_disconnected_stripe_is_not_a_beam():
    image = _page(((145, 8, "quarter", "down"), (360, 6, "quarter", "down")))
    ImageDraw.Draw(image).line((136, 129, 307, 142), fill="black", width=5)
    detected = detect_staffs(image)
    staff = detected.staffs[0]
    heads = detect_noteheads(image, staff, detected.threshold, 110, 410)
    stems = linked_stems(image, staff, detected.threshold, heads)
    marks = detect_rhythm_evidence(image, staff, detected.threshold, heads, stems)
    assert len(heads) == 2
    assert not any(mark.kind == "beam" and mark.status == "accepted" for mark in marks)


def test_barline_blocks_beam_relation_even_when_ink_crosses_it():
    image = _page(
        ((145, 8, "eighth", "down"), (360, 6, "eighth", "down")),
        beam_groups=((0, 1),),
    )
    detected = detect_staffs(image)
    staff = detected.staffs[0]
    heads = detect_noteheads(image, staff, detected.threshold, 110, 410)
    stems = linked_stems(image, staff, detected.threshold, heads)
    bar = BarlineCandidate(
        "bar", 250, Region(250, 74, 250, 138), 1.0, "accepted", "test"
    )
    marks = detect_rhythm_evidence(
        image, staff, detected.threshold, heads, stems, barlines=(bar,)
    )
    assert not any(mark.kind == "beam" and mark.status == "accepted" for mark in marks)


@pytest.mark.parametrize("spacing", [12, 16, 20])
def test_nearby_real_hollow_head_survives_ghost_filter(spacing):
    image = _page(
        (
            (145, 2, "quarter", "up"),
            (145 + round(1.2 * spacing), 7, "half", "down"),
        ),
        spacing=spacing,
    )
    detected = detect_staffs(image)
    staff = detected.staffs[0]
    heads = detect_noteheads(image, staff, detected.threshold, 110, 410)
    assert [(head.visual_kind, head.center_y) for head in heads] == [
        ("filled", 138 - spacing),
        ("hollow", 138 - round(3.5 * spacing)),
    ]


def test_full_page_without_manual_crop_keeps_note_coordinates():
    exercise = _page(
        (
            (145, 9, "eighth", "down"),
            (215, 7, "quarter", "down"),
            (285, 8, "eighth", "down"),
            (355, 4, "half", "up"),
        ),
        down_flag_right=True,
    )
    page = Image.new("RGB", (2000, 900), "white")
    page.paste(exercise, (400, 350))
    score = transcribe_one_measure(page, measure_left=510, measure_right=810)
    notes = score.parts[0].measures[0].notes
    assert [note.duration.kind for note in notes] == [
        "eighth",
        "quarter",
        "eighth",
        "half",
    ]
    assert [note.source_region.left for note in notes] == [535, 605, 675, 745]
    assert score.issues() == ()


def test_complete_double_beam_group_is_four_sixteenths_in_one_quarter():
    image = _page(
        (
            (145, 9, "eighth", "down"),
            (215, 8, "eighth", "down"),
            (285, 7, "eighth", "down"),
            (355, 6, "eighth", "down"),
        ),
        beam_groups=((0, 1, 2, 3),),
        double=True,
    )
    score = transcribe_one_measure(
        image, measure_left=110, measure_right=410, beats=1
    )
    notes = score.parts[0].measures[0].notes
    assert len(notes) == 4
    assert [note.duration.kind for note in notes] == ["sixteenth"] * 4
    assert [note.beam for note in notes] == [
        "begin", "continue", "continue", "end"
    ]
    assert all("double_beam" in note.diagnostics for note in notes)
    assert score.issues() == ()
    xml = ET.fromstring(to_musicxml(score))
    assert xml.findtext("./part/measure/attributes/divisions") == "4"
    assert [n.findtext("duration") for n in xml.findall("./part/measure/note")] == [
        "1", "1", "1", "1"
    ]
    assert [n.findtext("type") for n in xml.findall("./part/measure/note")] == [
        "16th", "16th", "16th", "16th"
    ]
    for number in ("1", "2"):
        beams = [
            n.find(f"beam[@number='{number}']").text
            for n in xml.findall("./part/measure/note")
        ]
        assert beams == ["begin", "continue", "continue", "end"]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("dev_eighth_flags.musicxml", 4),
        ("dev_eighth_pair.musicxml", 4),
        ("dev_eighth_beams.musicxml", 5),
        ("holdout_eighth_mix.musicxml", 6),
        ("dev_down_flags.musicxml", 4),
        ("dev_long_beam.musicxml", 5),
        ("blind_down_flags.musicxml", 4),
        ("blind_long_beam.musicxml", 5),
    ],
)
def test_musical_references_are_independent_and_rational(name, expected):
    root = ET.parse(REFERENCES / name).getroot()
    notes = root.findall("./part/measure/note")
    assert len(notes) == expected
    assert sum(Fraction(int(n.findtext("duration")), 2) for n in notes) == 4


def test_evaluator_counts_eighth_duration_error():
    image = _page(
        (
            (145, 2, "quarter", "up"),
            (215, 4, "quarter", "up"),
            (285, 3, "quarter", "up"),
            (355, 5, "half", "down"),
        )
    )
    result = evaluate_music(
        (REFERENCES / "dev_eighth_flags.musicxml").read_bytes(), _score(image)
    )
    assert result["duration_errors"] >= 1
    assert result["matches"] < result["reference_events"]


def test_eighths_keep_measure_boundaries_and_beams():
    image = _page(
        (
            (135, 2, "eighth", "up"),
            (170, 3, "eighth", "up"),
            (205, 4, "quarter", "up"),
            (235, 5, "half", "down"),
            (290, 2, "eighth", "up"),
            (325, 3, "quarter", "up"),
            (365, 4, "eighth", "up"),
            (405, 5, "half", "down"),
        ),
        beam_groups=((0, 1),),
    )
    ImageDraw.Draw(image).line((260, 74, 260, 138), fill="black", width=2)
    result = transcribe_measures(image, content_left=110, content_right=430)
    assert len(result.score.parts[0].measures) == 2
    assert [len(measure.notes) for measure in result.score.parts[0].measures] == [4, 4]
    assert result.score.issues() == ()
    root = ET.fromstring(to_musicxml(result.score))
    assert len(root.findall("./part/measure")) == 2
    assert [note.findtext("beam") for note in root.findall("./part/measure/note")][
        :2
    ] == ["begin", "end"]
