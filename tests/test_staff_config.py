"""Contrato de configuração da geometria sem alterar os resultados padrão."""

from dataclasses import asdict

import pytest
from PIL import Image, ImageDraw

from fluteomr import StaffDetectionConfig, detect_staffs, detect_staffs_file


def _page():
    image = Image.new("RGB", (400, 155), "white")
    draw = ImageDraw.Draw(image)
    for y in (30, 45, 60, 75, 90):
        draw.line((10, y, 380, y), fill="black", width=2)
    return image


def test_default_config_preserves_legacy_detection(tmp_path):
    page = _page()
    path = tmp_path / "staff.png"
    page.save(path)
    default = detect_staffs(page)
    explicitly_configured = detect_staffs(page, config=StaffDetectionConfig())
    assert default == explicitly_configured
    assert default.status == "detected"
    assert default.staff_count == 1
    assert detect_staffs_file(path, config=StaffDetectionConfig()) == default
    assert asdict(StaffDetectionConfig()) == {
        "primary_span_fraction": 0.25,
        "retry_span_fraction": 0.10,
        "projection_peak_fraction": 0.60,
        "contrast_adjust_fraction": 0.30,
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("primary_span_fraction", 0),
        ("retry_span_fraction", -0.1),
        ("projection_peak_fraction", float("nan")),
        ("contrast_adjust_fraction", float("inf")),
        ("contrast_adjust_fraction", 1.1),
        ("primary_span_fraction", True),
    ],
)
def test_invalid_config_is_rejected(name, value):
    with pytest.raises(ValueError):
        StaffDetectionConfig(**{name: value})


def test_only_typed_configs_are_accepted():
    with pytest.raises(TypeError, match="StaffDetectionConfig"):
        detect_staffs(_page(), config={"primary_span_fraction": 0.25})
