"""Operações do anotador sem janela nem dependência de Tkinter."""

import json

import pytest
from PIL import Image

from fluteomr.annotation_editor import (
    AnnotationEditor,
    canvas_to_image,
    drag_box,
    hit_box,
    image_to_canvas,
    move_box,
    next_pending_clef,
    resize_box,
)
from fluteomr.annotations import AnnotationError, image_sha256, load_reference, verify_image


def _draft(tmp_path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    path = image_dir / "page.png"
    Image.new("RGB", (200, 120), "white").save(path)
    lines = [{"x_start": 20, "x_end": 150, "y": y} for y in (30, 40, 50, 60, 70)]
    data = {
        "schema_version": 1,
        "kind": "reference",
        "split": "unspecified",
        "review": {"status": "draft", "confirmed_by": None},
        "image": {
            "id": "page",
            "filename": "page.png",
            "sha256": image_sha256(path),
            "width": 200,
            "height": 120,
        },
        "coverage": {"staffs": "unknown", "systems": "unknown", "clefs": "unknown"},
        "staffs": [
            {
                "id": "s0",
                "order": 0,
                "review_state": "unknown",
                "region": {"left": 20, "top": 30, "right": 150, "bottom": 70},
                "lines": lines,
            }
        ],
        "systems": [
            {
                "id": "sys0",
                "order": 0,
                "staff_ids": ["s0"],
                "review_state": "uncertain",
                "partial_visible": False,
            }
        ],
        "clefs": [{"staff_id": "s0", "state": "unknown", "kind": None, "region": None}],
    }
    draft_path = tmp_path / "page.reference-draft.json"
    draft_path.write_text(json.dumps(data), encoding="utf-8")
    return draft_path, image_dir


def test_read_valid_draft_and_reject_invalid_json(tmp_path):
    path, images = _draft(tmp_path)
    editor = AnnotationEditor(path, images)
    assert editor.size == (200, 120)
    assert editor.data["review"]["status"] == "draft"
    assert not editor.dirty
    bad = tmp_path / "broken.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(AnnotationError, match="JSON inválido"):
        AnnotationEditor(bad, images)


def test_image_canvas_coordinates_and_bounds():
    assert image_to_canvas(13, 17, 0.5) == (6.5, 8.5)
    assert canvas_to_image(6.5, 8.5, 0.5, 200, 120) == (13, 17)
    assert canvas_to_image(-80, 9999, 2, 200, 120) == (0, 119)
    with pytest.raises(ValueError, match="zoom"):
        canvas_to_image(1, 1, 0, 200, 120)


def test_box_creation_movement_resize_and_limits():
    assert drag_box((18, 30), (4, 8)) == {
        "left": 4,
        "top": 8,
        "right": 18,
        "bottom": 30,
    }
    with pytest.raises(AnnotationError, match="largura"):
        drag_box((4, 8), (4, 9))
    box = {"left": 20, "top": 30, "right": 150, "bottom": 70}
    assert move_box(box, 1000, -1000, 200, 120) == {
        "left": 69,
        "top": 0,
        "right": 199,
        "bottom": 40,
    }
    assert resize_box(box, 10, 200, 200, 120) == {
        "left": 20,
        "top": 30,
        "right": 21,
        "bottom": 119,
    }


def test_moving_staff_moves_lines_and_invalid_resize_is_transactional(tmp_path):
    path, images = _draft(tmp_path)
    editor = AnnotationEditor(path, images)
    moved = move_box(editor.box("staffs", "s0"), 10, 5, *editor.size)
    editor.set_box("staffs", "s0", moved, move=True)
    assert editor.item("staffs", "s0")["lines"][0] == {
        "x_start": 30,
        "x_end": 160,
        "y": 35,
    }
    before = editor.data.copy()
    with pytest.raises(AnnotationError, match="fora da região"):
        editor.set_box(
            "staffs",
            "s0",
            {"left": 30, "top": 35, "right": 100, "bottom": 75},
        )
    assert editor.data == before
    editor.set_box("staffs", "s0", resize_box(moved, 170, 80, *editor.size))
    assert editor.box("staffs", "s0")["right"] == 170
    assert editor.dirty
    editor.revert()
    assert editor.box("staffs", "s0")["left"] == 20
    assert not editor.dirty


def test_clef_review_round_trip_preserves_unedited_fields(tmp_path):
    path, images = _draft(tmp_path)
    original = load_reference(path)
    editor = AnnotationEditor(path, images)
    box = {"left": 22, "top": 20, "right": 35, "bottom": 80}
    editor.update_clef("s0", state="present", kind="treble", region=box)
    editor.update_page(
        split="development",
        coverage={"staffs": "unknown", "systems": "unknown", "clefs": "unknown"},
    )
    assert editor.dirty
    editor.save()
    reopened = AnnotationEditor(path, images)
    assert reopened.item("clefs", "s0")["region"] == box
    assert reopened.data["staffs"] == original["staffs"]
    assert reopened.data["image"] == original["image"]
    assert reopened.data["review"] == original["review"]
    assert not reopened.dirty
    reopened.check()


def test_add_delete_keep_references_consistent(tmp_path):
    path, images = _draft(tmp_path)
    editor = AnnotationEditor(path, images)
    second = editor.add_staff({"left": 20, "top": 80, "right": 150, "bottom": 110})
    assert second == "s1"
    assert editor.item("clefs", second)["state"] == "unknown"
    new_system = editor.add_system([second])
    assert editor.box("systems", new_system)["bottom"] == 110
    editor.delete("staffs", second)
    assert [item["id"] for item in editor.data["systems"]] == ["sys0"]
    assert [item["staff_id"] for item in editor.data["clefs"]] == ["s0"]
    assert editor.data["coverage"] == {
        "staffs": "unknown",
        "systems": "unknown",
        "clefs": "unknown",
    }
    editor.check()


def test_inserted_staff_keeps_vertical_order_and_rejects_empty_box(tmp_path):
    path, images = _draft(tmp_path)
    editor = AnnotationEditor(path, images)
    with pytest.raises(AnnotationError, match="largura"):
        editor.add_staff({"left": 5, "top": 5, "right": 5, "bottom": 20})
    added = editor.add_staff({"left": 10, "top": 5, "right": 100, "bottom": 25})
    assert [item["id"] for item in editor.data["staffs"]] == [added, "s0"]
    assert [item["order"] for item in editor.data["staffs"]] == [0, 1]
    assert editor.item("clefs", added)["state"] == "unknown"


def test_save_guards_existing_and_validated_references(tmp_path):
    path, images = _draft(tmp_path)
    editor = AnnotationEditor(path, images)
    editor.update_clef("s0", state="present", kind="treble", region=None)
    target = tmp_path / "existing.json"
    target.write_text("do not touch", encoding="utf-8")
    with pytest.raises(FileExistsError):
        editor.save(target)
    assert target.read_text() == "do not touch"
    path.write_text(path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(AnnotationError, match="mudou no disco"):
        editor.save()

    data = load_reference(path)
    data["split"] = "development"
    data["review"] = {"status": "validated", "confirmed_by": "human"}
    data["staffs"][0]["review_state"] = "confirmed"
    path.write_text(json.dumps(data), encoding="utf-8")
    validated = AnnotationEditor(path, images)
    assert not validated.editable
    with pytest.raises(PermissionError, match="somente leitura"):
        validated.save(tmp_path / "copy.json")


def test_pending_navigation_is_read_only_and_skips_reviewed(tmp_path):
    path, images = _draft(tmp_path)
    editor = AnnotationEditor(path, images)
    editor.add_staff({"left": 20, "top": 80, "right": 150, "bottom": 110})
    assert next_pending_clef(editor.data, "s0") == "s1"
    assert next_pending_clef(editor.data, "s1") == "s0"
    editor.update_clef("s0", state="absent", kind=None, region=None)
    snapshot = json.dumps(editor.data, sort_keys=True)
    assert next_pending_clef(editor.data, "s0") == "s1"
    assert next_pending_clef(editor.data, "s1") is None
    assert json.dumps(editor.data, sort_keys=True) == snapshot


def test_explicit_suggestion_confirmation_and_rejection(tmp_path):
    path, images = _draft(tmp_path)
    editor = AnnotationEditor(path, images)
    box = {"left": 22, "top": 20, "right": 35, "bottom": 80}
    for proposal in (None, {"status": "inconclusive", "region": None}):
        with pytest.raises(AnnotationError, match="não há sugestão"):
            editor.confirm_treble_suggestion("s0", proposal)
    assert not editor.dirty
    editor.confirm_treble_suggestion("s0", {"status": "detected", "region": box})
    assert editor.item("clefs", "s0") == {
        "staff_id": "s0",
        "state": "present",
        "kind": "treble",
        "region": box,
    }
    assert editor.data["review"]["status"] == "draft"
    box["left"] = 99
    assert editor.box("clefs", "s0")["left"] == 22


def test_inconclusive_clef_manual_correction_cancel_and_persistence(tmp_path):
    path, images = _draft(tmp_path)
    editor = AnnotationEditor(path, images)
    box = drag_box((21, 19), (39, 81))
    assert editor.item("clefs", "s0")["state"] == "unknown"
    assert not editor.dirty  # desenhar/cancelar uma prévia não edita o modelo
    editor.review_clef("s0", "treble", box)
    editor.save()
    reopened = AnnotationEditor(path, images)
    assert reopened.box("clefs", "s0") == box
    assert reopened.data["review"]["status"] == "draft"
    assert not reopened.dirty


def test_zoom_mapping_and_clef_hit_priority():
    for zoom in (0.25, 0.75, 1, 2, 4):
        x, y = image_to_canvas(32, 44, zoom)
        assert canvas_to_image(x, y, zoom, 200, 120) == (32, 44)
    staff = {"left": 10, "top": 20, "right": 190, "bottom": 90}
    clef = {"left": 20, "top": 25, "right": 40, "bottom": 80}
    boxes = [("staffs", "s0", staff), ("clefs", "s0", clef)]
    assert hit_box((30, 40), boxes) == ("clefs", "s0")
    assert hit_box((180, 40), boxes) == ("staffs", "s0")
    assert hit_box((0, 0), boxes) is None


def test_annotation_image_rejects_traversal_and_escaping_symlinks(tmp_path):
    reference_path, image_dir = _draft(tmp_path)
    reference = load_reference(reference_path)
    assert verify_image(reference, image_dir) == image_dir / "page.png"

    outside = tmp_path / "outside.png"
    Image.new("RGB", (200, 120), "black").save(outside)
    reference["image"]["sha256"] = image_sha256(outside)
    for untrusted in ("../outside.png", str(outside), "..\\outside.png"):
        reference["image"]["filename"] = untrusted
        with pytest.raises(AnnotationError, match="nome simples"):
            verify_image(reference, image_dir)

    symlink = image_dir / "alias.png"
    try:
        symlink.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks indisponíveis nesta plataforma")
    reference["image"]["filename"] = "alias.png"
    with pytest.raises(AnnotationError, match="fora do diretório"):
        verify_image(reference, image_dir)
