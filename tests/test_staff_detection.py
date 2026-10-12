"""Ground truth sintético independente da implementação do detector."""

import json
import subprocess
import sys

import pytest
from PIL import Image, ImageDraw, ImageFilter

from fluteomr import detect_staffs, detect_staffs_file, image_io
from fluteomr.debug import render_debug_image
from fluteomr.image_io import load_image
from tools.staff_examples import examples, make_staff_image


@pytest.mark.parametrize(
    "case", [c for c in examples() if c.supported], ids=lambda c: c.name
)
def test_synthetic_ground_truth(case):
    result = detect_staffs(case.image)

    assert result.status == case.expected_status
    assert result.staff_count == len(case.centers)
    assert (result.width, result.height) == case.image.size
    for staff, expected in zip(result.staffs, case.centers, strict=True):
        assert len(staff.lines) == 5
        assert [line.y for line in staff.lines] == sorted(
            line.y for line in staff.lines
        )
        for line, center in zip(staff.lines, expected, strict=True):
            assert abs(line.y - center) <= 2
            assert 0 <= line.x_start < line.x_end < result.width
            assert line.thickness > 0
            assert staff.region.top <= line.y <= staff.region.bottom
        assert abs(staff.spacing - (expected[1] - expected[0])) <= 1
    assert result.to_dict()["staff_count"] == len(case.centers)


@pytest.mark.parametrize("extension", ["png", "jpg"])
def test_file_input_and_horizontal_extents(tmp_path, extension):
    image, expected = make_staff_image()
    path = tmp_path / f"input.{extension}"
    image.save(path)
    result = detect_staffs_file(path)
    assert result.status == "detected"
    assert result.staff_count == 1
    for line, y in zip(result.staffs[0].lines, expected[0], strict=True):
        assert abs(line.y - y) <= 2
        assert abs(line.x_start - 38) <= 2
        assert abs(line.x_end - 601) <= 2


def test_transparent_background_and_input_not_mutated():
    image = Image.new("RGBA", (320, 140), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y in [20, 32, 44, 56, 68]:
        draw.line((20, y, 299, y), fill=(0, 0, 0, 255))
    before = image.tobytes()
    assert detect_staffs(image).staff_count == 1
    assert image.tobytes() == before


def test_short_marks_do_not_become_lines():
    image = Image.new("RGB", (320, 140), "white")
    draw = ImageDraw.Draw(image)
    for y in [20, 32, 44, 56, 68]:
        draw.line((100, y, 125, y), "black")
    assert detect_staffs(image).status == "no_staff"


def test_five_filled_bands_are_not_staff_lines():
    image, _ = make_staff_image(spacing=12, thickness=8)
    assert detect_staffs(image).status == "no_staff"


def test_lines_without_common_horizontal_region_are_rejected():
    image = Image.new("RGB", (400, 160), "white")
    draw = ImageDraw.Draw(image)
    for i in range(5):
        start = 0 if i % 2 else 240
        draw.line((start, 20 + 12 * i, start + 150, 20 + 12 * i), "black")
    assert detect_staffs(image).status == "no_staff"


def test_uniform_black_image_is_not_staff():
    assert detect_staffs(Image.new("L", (320, 140), 0)).status == "no_staff"


def test_light_gray_lines_are_detected():
    image, _ = make_staff_image()
    image = image.convert("L").point(lambda value: 150 if value == 0 else 240)
    assert detect_staffs(image).staff_count == 1


def test_debug_image_dimensions_and_overlay():
    image, _ = make_staff_image()
    before = image.tobytes()
    result = detect_staffs(image)
    debug = render_debug_image(image, result)
    assert debug.size == image.size
    assert debug.getpixel((100, 52)) == (255, 0, 0)
    assert image.tobytes() == before
    with pytest.raises(ValueError, match="Dimensões"):
        render_debug_image(Image.new("RGB", (5, 5)), result)


def test_unsupported_format_and_invalid_file(tmp_path):
    path = tmp_path / "input.bmp"
    Image.new("RGB", (10, 10)).save(path)
    with pytest.raises(ValueError, match="PNG ou JPEG"):
        load_image(path)
    path.write_bytes(b"not an image")
    with pytest.raises(Image.UnidentifiedImageError):
        load_image(path)


def test_cli_json_and_debug_output(tmp_path):
    image, _ = make_staff_image()
    source, output = tmp_path / "input.png", tmp_path / "debug.png"
    image.save(source)
    run = subprocess.run(
        [sys.executable, "-m", "fluteomr", str(source), "--debug", str(output)],
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(run.stdout)
    assert result["staff_count"] == 1
    assert result["status"] == "detected"
    assert len(result["staffs"][0]["lines"]) == 5
    with Image.open(output) as debug:
        assert debug.size == image.size
    for target in [source, output]:
        failed = subprocess.run(
            [sys.executable, "-m", "fluteomr", str(source), "--debug", str(target)],
            text=True,
            capture_output=True,
        )
        assert failed.returncode == 2
        assert not failed.stdout


def test_cli_reports_missing_input(tmp_path):
    run = subprocess.run(
        [sys.executable, "-m", "fluteomr", str(tmp_path / "absent.png")],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 2
    assert not run.stdout


@pytest.mark.xfail(
    strict=True, reason="Geometria não distingue cinco linhas não musicais"
)
def test_nonmusical_ruling_should_not_be_a_musical_staff():
    case = next(case for case in examples() if case.name == "nonmusical_ruling")
    result = detect_staffs(case.image)
    assert "horizontal_geometry_only" in result.diagnostics
    assert result.staff_count == 0


@pytest.mark.xfail(
    strict=True, reason="Projeção horizontal não corrige inclinação de 2°"
)
def test_two_degree_skew_should_preserve_staff():
    case = next(case for case in examples() if case.name == "skew_2_degrees")
    result = detect_staffs(case.image)
    assert result.staff_count == 1


def test_ambiguous_group_preserves_an_independent_staff():
    image = Image.new("RGB", (320, 260), "white")
    draw = ImageDraw.Draw(image)
    for y in [20, 32, 44, 56, 68, 80, 150, 162, 174, 186, 198]:
        draw.line((20, y, 299, y), "black")
    result = detect_staffs(image)
    assert result.status == "ambiguous"
    assert result.staff_count == 1
    assert [line.y for line in result.staffs[0].lines] == [150, 162, 174, 186, 198]
    assert len(result.candidates) == 11


def test_zero_size_and_pixel_limit_are_rejected(monkeypatch):
    with pytest.raises(ValueError, match="positivas"):
        detect_staffs(Image.new("L", (0, 5)))
    monkeypatch.setattr(image_io, "MAX_PIXELS", 100)
    with pytest.raises(ValueError, match="limite"):
        detect_staffs(Image.new("L", (11, 10)))


def test_exif_rotation_uses_normalized_coordinates(tmp_path):
    image, centers = make_staff_image()
    rotated = image.transpose(Image.Transpose.ROTATE_90)
    exif = Image.Exif()
    exif[274] = 6  # Orientação armazenada: girar 90 graus no sentido horário.
    path = tmp_path / "oriented.jpg"
    rotated.save(path, exif=exif)
    result = detect_staffs_file(path)
    assert (result.width, result.height) == image.size
    assert result.staff_count == 1
    for line, y in zip(result.staffs[0].lines, centers[0], strict=True):
        assert abs(line.y - y) <= 2


def test_unequal_horizontal_extents_and_irregular_pixel_spacing():
    image = Image.new("L", (400, 150), 255)
    draw = ImageDraw.Draw(image)
    positions = [40, 47, 56, 64, 71]
    for index, y in enumerate(positions):
        start, end = (20, 300) if index % 2 == 0 else (100, 380)
        draw.line((start, y, end, y), fill=0)
        draw.rectangle((180, y, 183, y), fill=255)
        draw.line((220, y - 4, 220, y + 3), fill=0)
    result = detect_staffs(image)
    assert result.status == "detected"
    assert result.staff_count == 1
    assert [round(line.y) for line in result.staffs[0].lines] == positions
    assert result.staffs[0].region.left <= 20
    assert result.staffs[0].region.right >= 380


def test_faint_blurred_jpeg_lines_with_darker_symbols(tmp_path):
    image = Image.new("L", (640, 160), 250)
    draw = ImageDraw.Draw(image)
    centers = [40, 52, 64, 76, 88]
    for y in centers:
        draw.line((35, y, 605, y), fill=205)
    for y in [30, 42, 54, 66, 78, 90]:
        draw.ellipse((8, y, 28, y + 7), fill=0)
    path = tmp_path / "faint.jpg"
    image.filter(ImageFilter.GaussianBlur(0.35)).save(path, quality=45)
    result = detect_staffs_file(path)
    assert result.staff_count == 1
    assert "contrast_retry" in result.diagnostics
    assert result.threshold < result.analysis_threshold
    assert all(
        abs(line.y - center) <= 2
        for line, center in zip(result.staffs[0].lines, centers, strict=True)
    )


def test_multiple_tightly_spaced_systems_with_symbols():
    image, expected = make_staff_image(
        size=(480, 230), tops=(15, 85, 155), spacing=7, symbols=True, gaps=True
    )
    result = detect_staffs(image)
    assert result.staff_count == 3
    for staff, centers in zip(result.staffs, expected, strict=True):
        assert len(staff.lines) == 5
        assert all(
            abs(line.y - center) <= 2
            for line, center in zip(staff.lines, centers, strict=True)
        )


def test_unrelated_horizontal_rules_remain_rejected():
    image = Image.new("L", (400, 160), 255)
    draw = ImageDraw.Draw(image)
    for y, length in [(15, 350), (28, 300), (43, 330), (66, 340), (89, 310)]:
        draw.line((10, y, length, y), fill=0)
    assert detect_staffs(image).status == "no_staff"
