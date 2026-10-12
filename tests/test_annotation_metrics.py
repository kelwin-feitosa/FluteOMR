"""Métricas com entradas controladas, sem usar os detectores sob avaliação."""

import copy
import json

import pytest
from PIL import Image

from fluteomr.annotations import (
    AnnotationError,
    image_sha256,
    load_reference,
    validate_reference,
    verify_image,
)
from fluteomr.metrics import (
    NOT_EVALUABLE,
    aggregate_reports,
    evaluate_page,
    match_staffs,
)


def box(top: int, bottom: int, left: int = 20, right: int = 400):
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def staff(staff_id: str, order: int, top: int):
    return {
        "id": staff_id,
        "order": order,
        "review_state": "confirmed",
        "region": box(top, top + 40),
        "lines": [{"x_start": 20, "x_end": 400, "y": top + 10 * i} for i in range(5)],
    }


def reference():
    return {
        "schema_version": 1,
        "kind": "reference",
        "split": "test",
        "review": {"status": "validated", "confirmed_by": "test-reviewer"},
        "image": {
            "id": "controlled",
            "filename": "controlled.png",
            "sha256": "0" * 64,
            "width": 500,
            "height": 300,
        },
        "coverage": {"staffs": "complete", "systems": "complete", "clefs": "complete"},
        "staffs": [staff("a", 0, 20), staff("b", 1, 100)],
        "systems": [
            {
                "id": "sys0",
                "order": 0,
                "staff_ids": ["a", "b"],
                "review_state": "confirmed",
                "partial_visible": False,
            }
        ],
        "clefs": [
            {
                "staff_id": "a",
                "state": "present",
                "kind": "treble",
                "region": box(10, 70, 25, 45),
            },
            {"staff_id": "b", "state": "absent", "kind": None, "region": None},
        ],
    }


def prediction():
    ref = reference()
    return {
        "staffs": [
            {"region": item["region"].copy(), "lines": copy.deepcopy(item["lines"])}
            for item in ref["staffs"]
        ],
        "systems": {"status": "grouped", "groups": [[0, 1]]},
        "clefs": [
            {"status": "detected", "region": box(10, 70, 25, 45)},
            {"status": "no_treble", "region": None},
        ],
    }


def test_perfect_spatial_match_system_and_clef():
    ref, pred = reference(), prediction()
    validate_reference(ref, require_validated=True)
    report = evaluate_page(ref, pred)
    assert report["staffs"]["tp"] == 2
    assert report["staffs"]["fp"] == report["staffs"]["fn"] == 0
    assert report["staffs"]["f1"] == 1
    assert report["staffs"]["line_y_mae_px"] == 0
    assert report["systems"]["correct_systems"] == 1
    assert report["systems"]["pair_tp"] == 1
    assert report["clefs"]["tp"] == 1
    assert report["clefs"]["tn"] == 1
    assert report["clefs"]["f1"] == 1


def test_missing_staff_is_false_negative():
    pred = prediction()
    pred["staffs"].pop()
    pred["systems"]["groups"] = [[0]]
    pred["clefs"].pop()
    report = evaluate_page(reference(), pred)
    assert (report["staffs"]["tp"], report["staffs"]["fp"], report["staffs"]["fn"]) == (
        1,
        0,
        1,
    )
    assert report["staffs"]["recall"] == 0.5


def test_extra_staff_is_false_positive():
    pred = prediction()
    pred["staffs"].append(
        {"region": box(200, 240), "lines": staff("x", 0, 200)["lines"]}
    )
    pred["systems"]["groups"].append([2])
    pred["clefs"].append({"status": "no_treble", "region": None})
    report = evaluate_page(reference(), pred)
    assert (report["staffs"]["tp"], report["staffs"]["fp"], report["staffs"]["fn"]) == (
        2,
        1,
        0,
    )


def test_equal_counts_wrong_positions_are_not_perfect():
    pred = prediction()
    pred["staffs"][1]["region"] = box(200, 240)
    pred["staffs"][1]["lines"] = staff("x", 0, 200)["lines"]
    report = evaluate_page(reference(), pred)
    assert (report["staffs"]["tp"], report["staffs"]["fp"], report["staffs"]["fn"]) == (
        1,
        1,
        1,
    )


def test_one_prediction_eligible_for_two_references_is_reported_ambiguous():
    refs = [staff("a", 0, 20), staff("b", 1, 24)]
    preds = [{"region": box(22, 62), "lines": staff("p", 0, 22)["lines"]}]
    matching = match_staffs(refs, preds)
    assert matching["ambiguous_prediction_indices"] == [0]
    assert len(matching["pairs"]) == 1


def test_two_candidates_for_one_reference_keep_one_to_one_matching():
    refs = [staff("a", 0, 20)]
    preds = [
        {"region": box(20, 60), "lines": staff("p", 0, 20)["lines"]},
        {"region": box(22, 62), "lines": staff("q", 0, 22)["lines"]},
    ]
    matching = match_staffs(refs, preds)
    assert matching["ambiguous_reference_ids"] == ["a"]
    assert len(matching["pairs"]) == 1
    assert matching["pairs"][0]["prediction_index"] == 0


def test_assignment_maximizes_cardinality_before_distance():
    refs = [staff("a", 0, 20), staff("b", 1, 24)]
    refs[1]["region"] = box(24, 64, 200, 400)
    preds = [
        {"region": box(23, 63, 200, 400), "lines": staff("p", 0, 23)["lines"]},
        {"region": box(20, 60, 20, 150), "lines": staff("q", 0, 20)["lines"]},
    ]
    matching = match_staffs(refs, preds)
    assert {p["reference_id"]: p["prediction_index"] for p in matching["pairs"]} == {
        "a": 1,
        "b": 0,
    }


def test_split_system_counts_pair_false_negative():
    pred = prediction()
    pred["systems"]["groups"] = [[0], [1]]
    report = evaluate_page(reference(), pred)
    assert report["systems"]["split_systems"] == 1
    assert report["systems"]["pair_fn"] == 1
    assert report["systems"]["correct_systems"] == 0


def test_merged_system_counts_pair_false_positive():
    ref = reference()
    ref["systems"] = [
        {
            "id": f"sys{i}",
            "order": i,
            "staff_ids": [staff_id],
            "review_state": "confirmed",
            "partial_visible": False,
        }
        for i, staff_id in enumerate(("a", "b"))
    ]
    report = evaluate_page(ref, prediction())
    assert report["systems"]["merged_systems"] == 1
    assert report["systems"]["pair_fp"] == 1
    assert report["systems"]["correct_systems"] == 0


def test_present_treble_not_detected_is_false_negative():
    pred = prediction()
    pred["clefs"][0] = {"status": "no_treble", "region": None}
    report = evaluate_page(reference(), pred)
    assert report["clefs"]["fn"] == 1
    assert report["clefs"]["recall"] == 0


def test_confirmed_absence_with_detection_is_false_positive():
    pred = prediction()
    pred["clefs"][1] = {"status": "detected", "region": box(90, 150, 25, 45)}
    report = evaluate_page(reference(), pred)
    assert report["clefs"]["fp"] == 1
    assert report["clefs"]["negative_false_positive_rate"] == 1


def test_unknown_clef_is_not_negative():
    ref, pred = reference(), prediction()
    ref["coverage"]["clefs"] = "partial"
    ref["clefs"][1] = {
        "staff_id": "b",
        "state": "unknown",
        "kind": None,
        "region": None,
    }
    pred["clefs"][1] = {"status": "detected", "region": box(90, 150, 25, 45)}
    report = evaluate_page(ref, pred)
    assert report["clefs"]["unknown"] == 1
    assert report["clefs"]["fp"] == 0
    assert report["clefs"]["unscored_detections"] == 1
    assert report["clefs"]["precision"] == NOT_EVALUABLE
    assert report["clefs"]["recall"] == 1


def test_inconclusive_positive_is_not_claimed_detected():
    pred = prediction()
    pred["clefs"][0] = {"status": "inconclusive", "region": None}
    report = evaluate_page(reference(), pred)
    assert report["clefs"]["inconclusive"] == 1
    assert report["clefs"]["fn"] == 1


def test_wrong_clef_box_counts_localization_failure():
    pred = prediction()
    pred["clefs"][0]["region"] = box(100, 160, 25, 45)
    report = evaluate_page(reference(), pred)
    assert report["clefs"]["wrong_location"] == 1
    assert report["clefs"]["negative_false_positive_rate"] == 0
    assert (report["clefs"]["tp"], report["clefs"]["fp"], report["clefs"]["fn"]) == (
        0,
        1,
        1,
    )


def test_partial_ground_truth_suppresses_global_staff_rates():
    ref = reference()
    ref["coverage"]["staffs"] = "partial"
    ref["coverage"]["systems"] = "partial"
    ref["coverage"]["clefs"] = "partial"
    ref["staffs"][1]["review_state"] = "unknown"
    ref["staffs"][1]["region"] = None
    ref["staffs"][1]["lines"] = None
    validate_reference(ref)
    report = evaluate_page(ref, prediction())
    assert report["staffs"]["matched_count"] == 1
    assert report["staffs"]["precision"] == NOT_EVALUABLE
    assert report["systems"]["correct_systems"] == NOT_EVALUABLE


def test_ambiguous_prediction_grouping_does_not_claim_system_accuracy():
    pred = prediction()
    pred["systems"]["status"] = "ambiguous"
    report = evaluate_page(reference(), pred)
    assert report["systems"]["status"] == NOT_EVALUABLE


def test_uncertain_reference_system_is_not_treated_as_confirmed():
    ref = reference()
    ref["coverage"]["systems"] = "partial"
    ref["systems"][0]["review_state"] = "uncertain"
    validate_reference(ref)
    assert evaluate_page(ref, prediction())["systems"]["status"] == NOT_EVALUABLE


def test_line_localization_errors_are_quantitative():
    pred = prediction()
    for line in pred["staffs"][0]["lines"]:
        line["y"] += 1
        line["x_start"] += 2
        line["x_end"] -= 2
    report = evaluate_page(reference(), pred)
    assert report["staffs"]["line_y_mae_px"] == 0.5
    assert report["staffs"]["line_endpoint_mae_px"] == 1
    assert report["staffs"]["line_y_count"] == 10


def test_blank_confirmed_page_with_extra_prediction_has_zero_precision():
    ref = reference()
    ref["staffs"] = []
    ref["systems"] = []
    ref["clefs"] = []
    pred = {
        "staffs": [prediction()["staffs"][0]],
        "systems": {"status": "grouped", "groups": [[0]]},
        "clefs": [{"status": "detected", "region": box(10, 70, 25, 45)}],
    }
    validate_reference(ref)
    report = evaluate_page(ref, pred)
    assert report["staffs"]["fp"] == 1
    assert report["staffs"]["precision"] == 0
    assert report["staffs"]["recall"] == NOT_EVALUABLE


def test_hash_mismatch_is_rejected(tmp_path):
    image_path = tmp_path / "controlled.png"
    Image.new("L", (500, 300), 255).save(image_path)
    ref = reference()
    ref["image"]["sha256"] = "f" * 64
    with pytest.raises(AnnotationError, match="hash SHA-256 diferente"):
        verify_image(ref, tmp_path)
    ref["image"]["sha256"] = image_sha256(image_path)
    assert verify_image(ref, tmp_path) == image_path


def test_invalid_json_and_inconsistent_references(tmp_path):
    path = tmp_path / "invalid.reference.json"
    path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(AnnotationError, match="JSON inválido"):
        load_reference(path)
    ref = reference()
    ref["staffs"][1]["id"] = "a"
    with pytest.raises(AnnotationError, match="duplicado"):
        validate_reference(ref)
    ref = reference()
    ref["systems"][0]["staff_ids"] = ["a", "missing"]
    with pytest.raises(AnnotationError, match="inexistente"):
        validate_reference(ref)
    ref = reference()
    ref["staffs"][0]["lines"][0]["y"] = -1
    with pytest.raises(AnnotationError, match="fora da região"):
        validate_reference(ref)


def test_empty_evaluation_has_no_artificial_perfect_scores():
    ref = reference()
    ref["staffs"] = []
    ref["systems"] = []
    ref["clefs"] = []
    pred = {"staffs": [], "systems": {"status": "empty", "groups": []}, "clefs": []}
    validate_reference(ref)
    report = evaluate_page(ref, pred)
    assert report["staffs"]["precision"] == NOT_EVALUABLE
    assert report["staffs"]["recall"] == NOT_EVALUABLE
    assert report["clefs"]["f1"] == NOT_EVALUABLE
    assert aggregate_reports([])["staffs"]["precision"] == NOT_EVALUABLE


def test_aggregate_localization_uses_annotated_line_denominator():
    first = evaluate_page(reference(), prediction())
    pred = prediction()
    pred["staffs"].pop()
    pred["systems"]["groups"] = [[0]]
    pred["clefs"].pop()
    for line in pred["staffs"][0]["lines"]:
        line["y"] += 3
    second = evaluate_page(reference(), pred)
    aggregate = aggregate_reports([first, second])
    assert aggregate["staffs"]["line_y_count"] == 15
    assert aggregate["staffs"]["line_y_mae_px"] == 1
    assert aggregate["staffs"]["tp"] == 3
    assert aggregate["staffs"]["fn"] == 1


def test_reference_round_trip_is_json_serializable():
    assert json.loads(json.dumps(reference())) == reference()
