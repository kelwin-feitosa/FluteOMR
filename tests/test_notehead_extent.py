"""Feixes longos não podem gerar uma sequência de cabeças preenchidas."""

from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from fluteomr.notes import detect_noteheads, pitch_from_y
from fluteomr.staff_detection import Region, Staff, StaffLine, detect_staffs
from fluteomr.transcription import transcribe_one_measure


@pytest.mark.parametrize("spacing", [10, 14, 20])
def test_continuous_shallow_beam_is_not_a_row_of_noteheads(spacing):
    image = Image.new("RGB", (500, 250), "white")
    draw = ImageDraw.Draw(image)
    for index in range(5):
        y = 100 + index * spacing
        draw.line((20, y, 480, y), fill="black", width=max(1, round(spacing / 10)))
    draw.line(
        (30, 100 - spacing, 470, 100 - 3 * spacing),
        fill="black",
        width=round(0.3 * spacing),
    )
    result = detect_staffs(image)
    assert result.staff_count == 1
    heads = detect_noteheads(image, result.staffs[0], result.threshold, 100, 400)
    assert heads == ()


@pytest.mark.parametrize("dpi", [150, 300])
def test_engraved_sloped_beam_preserves_exact_musical_events_without_ghosts(dpi):
    path = Path(__file__).parent / "data/music_lab/sprint1d/raster"
    with Image.open(path / f"beam-first-measure-{dpi}.png") as image:
        score = transcribe_one_measure(
            image, measure_left=0, measure_right=image.width - 1
        )
    notes = score.parts[0].measures[0].notes
    # Referência independente escrita para o primeiro compasso antes da inferência.
    expected = [("E", 4), ("G", 4), ("B", 4), ("D", 5), ("G", 5)]
    assert len(notes) == 5
    assert [(n.pitch.step, n.pitch.octave) for n in notes] == expected
    assert [n.duration.quarters for n in notes] == [Fraction(1, 2)] * 4 + [Fraction(2)]
    assert [n.beam for n in notes] == ["begin", "continue", "continue", "end", None]
    assert score.issues() == ()


@pytest.mark.parametrize("scale", [0.75, 1.0, 1.5])
def test_pitch_uses_local_line_geometry_instead_of_accumulated_spacing_error(scale):
    # Rasterização alterna intervalos de 10 e 10,5 px; o espaçamento mediano
    # não ancora corretamente a linha superior ao partir da linha inferior.
    ys = [93, 103.5, 113.5, 124, 134.5]
    lines = tuple(StaffLine(0, 400, y * scale, 1) for y in ys)
    staff = Staff(lines, 10.5 * scale, Region(0, 93 * scale, 400, 134.5 * scale))
    pitch = pitch_from_y(94 * scale, staff)
    assert pitch is not None
    assert (pitch.step, pitch.octave) == ("F", 5)
    for index, expected in enumerate(
        [("F", 5), ("D", 5), ("B", 4), ("G", 4), ("E", 4)]
    ):
        pitch = pitch_from_y(ys[index] * scale, staff)
        assert (pitch.step, pitch.octave) == expected
