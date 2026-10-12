"""Figuras próprias de clave e de símbolos negativos, sem template no detector."""

import json
import subprocess
import sys

from PIL import Image, ImageDraw

from fluteomr.clefs import detect_treble_clefs
from fluteomr.staff_detection import detect_staffs


def draw_treble(draw: ImageDraw.ImageDraw, left: int, top: int, spacing: int):
    s = spacing
    cx = left + 2 * s
    path = [
        (cx, top + s),
        (cx + 0.6 * s, top - 0.2 * s),
        (cx + 0.3 * s, top - 1.5 * s),
        (cx - 0.5 * s, top - 1.4 * s),
        (cx - 0.8 * s, top - 0.4 * s),
        (cx + 0.6 * s, top + s),
        (cx - 0.7 * s, top + 2.7 * s),
        (cx - 1.0 * s, top + 3.5 * s),
        (cx - 0.2 * s, top + 4.1 * s),
        (cx + 0.9 * s, top + 3.7 * s),
        (cx + 1.0 * s, top + 2.8 * s),
        (cx, top + 2.5 * s),
        (cx - 0.4 * s, top + 3.5 * s),
        (cx, top + 5.4 * s),
        (cx - 0.5 * s, top + 5.6 * s),
    ]
    draw.line(path, fill=0, width=max(2, round(s / 4)), joint="curve")


def make_image(
    *,
    spacing: int = 12,
    tops: tuple[int, ...] = (80,),
    clefs: tuple[bool, ...] = (True,),
    key: bool = False,
    notes: bool = False,
    broken: bool = False,
) -> Image.Image:
    width = 44 * spacing
    height = max(tops) + 9 * spacing
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    left = 3 * spacing
    for top, has_clef in zip(tops, clefs, strict=True):
        for rank in range(5):
            y = top + rank * spacing
            draw.line((left, y, width - spacing, y), fill=80)
        if has_clef:
            draw_treble(draw, left, top, spacing)
        if key:
            x = left + 6 * spacing
            for dx in (0, round(0.4 * spacing)):
                draw.line((x + dx, top, x + dx, top + 2.8 * spacing), fill=0)
            for dy in (spacing, 1.7 * spacing):
                draw.line((x - spacing / 3, top + dy, x + spacing, top + dy), fill=0)
        if notes:
            x = left + 10 * spacing
            draw.ellipse(
                (x, top + 2 * spacing, x + spacing, top + 2.6 * spacing), fill=0
            )
            draw.line((x + spacing, top + 2.2 * spacing, x + spacing, top), fill=0)
        if broken and has_clef:
            for rank in (1, 3):
                y = top + rank * spacing
                draw.line((left + spacing, y, left + 3 * spacing, y), fill=255)
    return image


def observations(image: Image.Image):
    staffs = detect_staffs(image)
    return staffs, detect_treble_clefs(image, staffs).observations


def test_isolated_clear_treble():
    staffs, result = observations(make_image())
    assert staffs.staff_count == 1
    assert result[0].status == "detected"
    assert result[0].clef.kind == "treble"
    assert result[0].clef.staff_index == 0
    assert result[0].clef.region.top < staffs.staffs[0].region.top


def test_different_scales():
    for spacing in (8, 12, 18):
        staffs, result = observations(make_image(spacing=spacing))
        assert staffs.staff_count == 1
        assert result[0].status == "detected", spacing


def test_key_signature_and_nearby_note_do_not_replace_clef():
    staffs, result = observations(make_image(key=True, notes=True))
    assert staffs.staff_count == 1
    assert result[0].status == "detected"
    assert result[0].clef.region.left < staffs.staffs[0].region.left + 5 * 12


def test_staff_without_clef_and_similar_c_clef_are_not_accepted():
    image = make_image(clefs=(False,), notes=True)
    staffs, result = observations(image)
    assert staffs.staff_count == 1
    assert result[0].status != "detected"
    image = make_image(clefs=(False,))
    draw = ImageDraw.Draw(image)
    # C-clave estilizada: duas curvas dentro das cinco linhas, sem cauda longa.
    draw.arc((50, 85, 82, 105), 90, 270, fill=0, width=2)
    draw.arc((50, 105, 82, 125), 90, 270, fill=0, width=2)
    _, result = observations(image)
    assert result[0].status != "detected"


def test_vertical_connector_and_bass_shape_are_not_treble():
    image = make_image(clefs=(False,))
    draw = ImageDraw.Draw(image)
    draw.line((36, 60, 36, 150), fill=0, width=2)
    draw.arc((55, 88, 80, 120), 260, 90, fill=0, width=3)
    draw.ellipse((82, 90, 85, 93), fill=0)
    draw.ellipse((82, 104, 85, 107), fill=0)
    _, result = observations(image)
    assert result[0].status != "detected"


def test_treble_with_line_interruptions():
    staffs, result = observations(make_image(broken=True))
    assert staffs.staff_count == 1
    assert result[0].status == "detected"


def test_multiple_systems_with_and_without_treble():
    image = make_image(tops=(70, 210, 350), clefs=(True, False, True))
    staffs, result = observations(image)
    assert staffs.staff_count == 3
    assert [item.status for item in result] == ["detected", "no_treble", "detected"]


def test_two_plausible_symbols_are_explicitly_inconclusive():
    image = make_image()
    draw_treble(ImageDraw.Draw(image), 36 + 4 * 12, 80, 12)
    _, result = observations(image)
    assert result[0].status == "inconclusive"
    assert result[0].clef is None


def test_mismatched_image_dimensions_are_rejected():
    image = make_image()
    detection = detect_staffs(image)
    from pytest import raises

    with raises(ValueError, match="Dimensões"):
        detect_treble_clefs(Image.new("L", (20, 20), 255), detection)


def test_cli_clefs_are_opt_in_and_debug_is_written(tmp_path):
    image_path = tmp_path / "clef.png"
    debug_path = tmp_path / "clef-debug.png"
    make_image().save(image_path)
    legacy = subprocess.run(
        [sys.executable, "-m", "fluteomr", str(image_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    enriched = subprocess.run(
        [
            sys.executable,
            "-m",
            "fluteomr",
            str(image_path),
            "--systems",
            "--clefs",
            "--debug",
            str(debug_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    old_data, new_data = json.loads(legacy.stdout), json.loads(enriched.stdout)
    assert {key: new_data[key] for key in old_data} == old_data
    assert "clef_detection" not in old_data
    assert new_data["clef_detection"]["observations"][0]["status"] == "detected"
    assert debug_path.exists()
