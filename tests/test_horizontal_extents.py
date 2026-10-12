"""Ground truth de limites horizontais, inclusive trechos interrompidos."""

from PIL import Image, ImageDraw

from fluteomr import detect_staffs


def test_staggered_interruptions_and_symbols_near_right_edge():
    image = Image.new("RGB", (440, 150), "white")
    draw = ImageDraw.Draw(image)
    centers = [30, 42, 54, 66, 78]
    for y, gap_start in zip(centers, [90, 145, 200, 250, 310], strict=True):
        draw.line((40, y, 380, y), fill="black")
        draw.rectangle((gap_start, y, gap_start + 25, y), fill="white")
    # Nota e haste próximas ao fim da pauta; não substituem a linha horizontal.
    draw.ellipse((352, 45, 365, 55), fill="black")
    draw.line((365, 50, 365, 25), fill="black")
    result = detect_staffs(image)
    assert result.staff_count == 1
    assert len(result.staffs[0].lines) == 5
    for line, center in zip(result.staffs[0].lines, centers, strict=True):
        assert abs(line.y - center) <= 1
        assert abs(line.x_start - 40) <= 2
        assert abs(line.x_end - 380) <= 2
    assert result.staffs[0].region.left == 40
    assert result.staffs[0].region.right == 380


def test_aligned_system_preserves_a_legitimately_shorter_staff():
    image = Image.new("L", (440, 265), 255)
    draw = ImageDraw.Draw(image)
    for top, right in [(15, 380), (100, 380), (185, 270)]:
        for offset in range(5):
            draw.line((40, top + offset * 10, right, top + offset * 10), fill=0)
    result = detect_staffs(image)
    assert result.staff_count == 3
    assert [staff.region.right for staff in result.staffs] == [380, 380, 270]
    for staff, right in zip(result.staffs, [380, 380, 270], strict=True):
        assert len(staff.lines) == 5
        assert all(abs(line.x_start - 40) <= 2 for line in staff.lines)
        assert all(abs(line.x_end - right) <= 2 for line in staff.lines)


def test_no_automatic_extension_to_image_margin_or_isolated_segment():
    image = Image.new("L", (500, 145), 255)
    draw = ImageDraw.Draw(image)
    for index in range(5):
        y = 25 + 12 * index
        draw.line((35, y, 300, y), fill=0)
        if index == 2:
            # Comprimento suficiente para virar fragmento, mas sem corroboração.
            draw.line((365, y, 405, y), fill=0)
    result = detect_staffs(image)
    assert result.staff_count == 1
    assert result.staffs[0].region.left == 35
    assert result.staffs[0].region.right == 300
    assert all(line.x_end == 300 for line in result.staffs[0].lines)


def test_short_staff_next_to_longer_system_is_not_extended():
    image = Image.new("L", (500, 220), 255)
    draw = ImageDraw.Draw(image)
    for top, end in [(20, 450), (120, 290)]:
        for index in range(5):
            draw.line((25, top + 12 * index, end, top + 12 * index), fill=0)
    result = detect_staffs(image)
    assert result.staff_count == 2
    assert [staff.region.right for staff in result.staffs] == [450, 290]
