"""Agrupamento de sistemas sem acoplar o teste à rasterização."""

import json
import subprocess
import sys

import pytest
from PIL import Image, ImageDraw

from fluteomr import detect_staffs, group_staffs
from fluteomr.staff_detection import Region, Staff, StaffLine


def make_staff(top: int, *, left: int = 20, right: int = 380) -> Staff:
    lines = tuple(StaffLine(left, right, top + 8 * i, 1) for i in range(5))
    return Staff(lines, 8, Region(left, top, right, top + 32))


def test_three_solo_systems_without_grouping_evidence():
    result = group_staffs(tuple(make_staff(top) for top in (20, 130, 240)))
    assert [s.staff_indices for s in result.systems] == [(0,), (1,), (2,)]
    assert result.status == "ambiguous"
    assert result.diagnostics == ("no_distinct_inter_system_gap",)


@pytest.mark.parametrize(
    ("tops", "expected"),
    [
        ((20, 70, 200, 250, 380, 430), ((0, 1), (2, 3), (4, 5))),
        (
            (20, 70, 120, 170, 300, 350, 400, 450),
            ((0, 1, 2, 3), (4, 5, 6, 7)),
        ),
        ((20, 69, 119, 169, 300, 351, 403, 456), ((0, 1, 2, 3), (4, 5, 6, 7))),
        ((20, 70, 200, 250, 300), ((0, 1), (2, 3, 4))),
    ],
)
def test_clear_gap_clusters(tops, expected):
    result = group_staffs(tuple(make_staff(top) for top in tops))
    assert result.status == "grouped"
    assert tuple(system.staff_indices for system in result.systems) == expected
    assert [system.id for system in result.systems] == list(range(len(expected)))


def test_small_horizontal_offset_and_legitimately_short_staff():
    staffs = (
        make_staff(20, left=20, right=380),
        make_staff(70, left=24, right=190),
        make_staff(200, left=25, right=375),
        make_staff(250, left=28, right=370),
    )
    result = group_staffs(staffs)
    assert [s.staff_indices for s in result.systems] == [(0, 1), (2, 3)]
    assert result.systems[0].region == Region(20, 20, 380, 102)
    assert result.systems[0].staffs[1] is staffs[1]


def test_uniform_ensemble_gaps_are_ambiguous():
    result = group_staffs(tuple(make_staff(top) for top in (20, 70, 120, 170)))
    assert result.status == "ambiguous"
    assert [s.staff_indices for s in result.systems] == [(0,), (1,), (2,), (3,)]


def test_nonoverlapping_horizontal_extents_are_ambiguous():
    staffs = (
        make_staff(20, left=20, right=140),
        make_staff(70, left=200, right=380),
        make_staff(200),
        make_staff(250),
    )
    result = group_staffs(staffs)
    assert result.status == "ambiguous"
    assert "weak_horizontal_alignment" in result.diagnostics


def test_empty_and_single_staff():
    assert group_staffs(()).status == "empty"
    result = group_staffs((make_staff(20),))
    assert result.status == "grouped"
    assert result.systems[0].staff_indices == (0,)


def test_image_pipeline_and_opt_in_cli(tmp_path):
    image = Image.new("L", (400, 350), 255)
    draw = ImageDraw.Draw(image)
    for top in (20, 70, 200, 250):
        for offset in range(0, 33, 8):
            draw.line((20, top + offset, 380, top + offset), fill=0)
    image_path = tmp_path / "systems.png"
    debug_path = tmp_path / "systems-debug.png"
    image.save(image_path)
    detection = detect_staffs(image)
    assert detection.staff_count == 4
    assert [s.staff_indices for s in group_staffs(detection.staffs).systems] == [
        (0, 1),
        (2, 3),
    ]
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
            "--debug",
            str(debug_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    old_data, new_data = json.loads(legacy.stdout), json.loads(enriched.stdout)
    assert "system_grouping" not in old_data
    assert {key: new_data[key] for key in old_data} == old_data
    assert new_data["system_grouping"]["system_count"] == 2
    assert debug_path.exists()
