"""Uma haste sem cabeça reconhecida não deve criar um compasso artificial."""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from fluteomr.staff_detection import Region, Staff, StaffLine, detect_staffs
from fluteomr.symbols import detect_barlines


@pytest.mark.parametrize("spacing", [10, 14, 20])
@pytest.mark.parametrize("direction", [-1, 1])
def test_unrecognized_hollow_head_stem_does_not_split_measure(spacing, direction):
    image = Image.new("L", (300, 200), 255)
    draw = ImageDraw.Draw(image)
    top, bottom = 40, 40 + 4 * spacing
    staff = Staff(
        tuple(StaffLine(10, 290, top + i * spacing, 1) for i in range(5)),
        spacing,
        Region(10, top, 290, bottom),
    )
    for line in staff.lines:
        draw.line((10, line.y, 290, line.y), fill=0)
    draw.line((230, top, 230, bottom), fill=0)
    # Cabeça no primeiro/último espaço e haste longa voltada para dentro.
    # A lista de cabeças fica vazia para reproduzir uma omissão do reconhecedor.
    y = top + spacing / 2 if direction == 1 else bottom - spacing / 2
    rx, ry = round(0.6 * spacing), round(0.3 * spacing)
    draw.ellipse((130 - rx, y - ry, 130 + rx, y + ry), outline=0, width=2)
    stem_x = 130 - rx if direction == 1 else 130 + rx
    draw.line((stem_x, y, stem_x, bottom if direction == 1 else top), fill=0)
    bars = detect_barlines(image, staff, 127, 20, 280)
    assert [bar.x for bar in bars if bar.status == "accepted"] == [230]
    stem = next(bar for bar in bars if abs(bar.x - stem_x) <= 1)
    assert stem.status == "inconclusive"
    assert stem.evidence == "unanchored_staff_endpoint"


def test_small_interior_gap_keeps_bar_with_supported_endpoints():
    image = Image.new("L", (300, 160), 255)
    draw = ImageDraw.Draw(image)
    staff = Staff(
        tuple(StaffLine(10, 290, 40 + i * 16, 1) for i in range(5)),
        16,
        Region(10, 40, 290, 104),
    )
    for line in staff.lines:
        draw.line((10, line.y, 290, line.y), fill=0)
    draw.line((150, 40, 150, 104), fill=0)
    draw.point((150, 62), fill=255)
    bars = detect_barlines(image, staff, 127, 20, 280)
    assert len(bars) == 1
    assert bars[0].status == "accepted"


@pytest.mark.parametrize("thickness", [1, 2, 3])
def test_true_bar_reaches_both_edges_with_different_staff_thicknesses(thickness):
    image = Image.new("L", (300, 160), 255)
    draw = ImageDraw.Draw(image)
    lines = []
    for i in range(5):
        y = 40 + i * 16
        draw.rectangle((10, y, 290, y + thickness - 1), fill=0)
        lines.append(StaffLine(10, 290, y + (thickness - 1) / 2, thickness))
    staff = Staff(tuple(lines), 16, Region(10, lines[0].y, 290, lines[-1].y))
    draw.line((150, 40, 150, 104 + thickness - 1), fill=0)
    bars = detect_barlines(image, staff, 127, 20, 280)
    assert [(bar.x, bar.status) for bar in bars] == [(150, "accepted")]


def test_engraved_development_excerpt_does_not_accept_missed_half_note_stem():
    path = (
        Path(__file__).parent
        / "data/music_lab/sprint1d/raster/barline-and-unrecognized-head-150.png"
    )
    with Image.open(path) as image:
        result = detect_staffs(image)
        assert result.staff_count == 1
        bars = detect_barlines(
            image, result.staffs[0], result.threshold, 0, image.width - 1
        )
    accepted = [bar for bar in bars if bar.status == "accepted"]
    # Geometria da renderização de uma referência própria, não predições.
    assert len(accepted) == 1
    assert abs(accepted[0].x - 32) <= 1
    stem = next(bar for bar in bars if abs(bar.x - 354) <= 1)
    assert stem.status == "inconclusive"
    assert stem.evidence == "unanchored_staff_endpoint"
