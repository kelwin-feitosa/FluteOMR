"""Cavidades de cabeças inclinadas não cabem necessariamente na máscara elíptica."""

from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from fluteomr.notes import _encloses_hole
from fluteomr.transcription import transcribe_one_measure


@pytest.mark.parametrize("open_outline", [False, True])
def test_cavity_connectivity_uses_context_beyond_ellipse_sample(open_outline):
    image = Image.new("L", (45, 45), 255)
    draw = ImageDraw.Draw(image)
    # Contorno inclinado; a cavidade branca alcança y=15, fora de y=20±4.
    draw.polygon(
        [(14, 20), (23, 12), (28, 14), (28, 20), (19, 27), (14, 26)], outline=0, width=2
    )
    if open_outline:
        draw.rectangle((22, 10, 26, 18), fill=255)
    assert _encloses_hole(image.tobytes(), 45, 127, 21, 20, 8, 4, 11) is (
        not open_outline
    )


@pytest.mark.parametrize("normalize", [False, True])
def test_150_dpi_half_note_on_space_completes_original_development_measure(normalize):
    path = (
        Path(__file__).parent
        / "data/music_lab/sprint1d/raster/barline-and-unrecognized-head-150.png"
    )
    with Image.open(path) as image:
        score = transcribe_one_measure(
            image,
            measure_left=40,
            measure_right=image.width - 1,
            normalize_heads=normalize,
        )
    notes = score.parts[0].measures[0].notes
    # Referência própria escrita antes da inferência: segundo compasso de
    # dev_register.musicxml. O XML não participa do reconhecimento.
    assert [(note.pitch.step, note.pitch.octave) for note in notes] == [
        ("A", 5),
        ("G", 5),
        ("F", 5),
        ("E", 5),
    ]
    assert [note.duration.quarters for note in notes] == [
        Fraction(1, 2),
        Fraction(1, 2),
        Fraction(1),
        Fraction(2),
    ]
    assert score.issues() == ()
