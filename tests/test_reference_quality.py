"""Referências humanas e geradas devem produzir evidências separadas."""

import json

import pytest

from tools.evaluate_music import evaluate_manifest, summarize_results


def _evaluated_row(identifier: str, status: str, expected: int, matched: int) -> dict:
    return {
        "id": identifier,
        "work_id": f"work-{identifier}",
        "reference_status": status,
        "evaluation": {
            "reference_events": expected,
            "matches": matched,
            "skipped_reference_events": 0,
            "measure_metrics": {
                "correct": int(expected == matched),
                "incorrect": int(expected != matched),
                "unevaluable": 0,
                "total": 1,
            },
        },
    }


def test_summary_never_conflates_human_and_generated_references():
    rows = [
        _evaluated_row("human", "validated", 4, 1),
        _evaluated_row("rendered", "source_authored", 20, 20),
        {
            "id": "pending",
            "work_id": "work-pending",
            "reference_status": "missing",
            "evaluation": "not_evaluated",
        },
    ]
    summary = summarize_results(rows)

    assert summary["match_fraction"] == {"matched": 21, "expected": 24}
    assert summary["reference_quality"]["validated"]["match_fraction"] == {
        "matched": 1,
        "expected": 4,
    }
    assert summary["reference_quality"]["source_authored"]["match_fraction"] == {
        "matched": 20,
        "expected": 20,
    }
    assert summary["reference_quality"]["missing"]["match_fraction"] == "not_evaluated"
    assert "source_authored" in summary["match_fraction_caveat"]


def test_declaring_human_validation_without_review_bundle_is_rejected(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format_version": 1,
                "examples": [
                    {
                        "id": "unverified",
                        "work_id": "test-work",
                        "split": "development",
                        "image": "missing-image.png",
                        "reference": "missing-reference.musicxml",
                        "reference_status": "validated",
                        "origin": "own_exercise",
                        "configured": {"measure_left": 10, "measure_right": 100},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pacote de revisão humana"):
        evaluate_manifest(manifest, tmp_path, continue_on_error=True)
