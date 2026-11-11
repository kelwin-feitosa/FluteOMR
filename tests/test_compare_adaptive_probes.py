"""Verifica comparação A/B sem transformar cobertura em precisão musical."""

import json

import pytest

from tools.compare_adaptive_probes import compare_files, compare_probe_reports


def _probe(adaptive: bool) -> dict:
    resolved = 3 if adaptive else 2
    return {
        "format_version": 2,
        "source_pdf": "source.pdf",
        "source_pdf_sha256": "a" * 64,
        "page_image_sha256": "b" * 64,
        "page_image_size": [480, 215],
        "page_number": 1,
        "dpi": 200,
        "status": "diagnostic_only",
        "experimental_adaptive_secondary": adaptive,
        "predicted_events": 4,
        "resolved_duration_events": resolved,
        "unresolved_duration_events": 4 - resolved,
        "predicted_double_beam_sixteenths": resolved - 2,
        "confirmed_mixed_beam_note_count": resolved - 2,
        "unresolved_duration_diagnostic_counts": {
            "secondary_stripe_ambiguous": 4 - resolved
        },
        "musical_accuracy": "not_evaluated",
        "xml_export": "not_attempted",
    }


def test_coverage_delta_never_claims_music_accuracy():
    result = compare_probe_reports(_probe(False), _probe(True))
    assert result["coverage_comparison"]["resolved_duration_events"] == {
        "baseline": 2,
        "adaptive": 3,
        "delta": 1,
    }
    assert result["unresolved_diagnostic_comparison"][
        "secondary_stripe_ambiguous"
    ]["delta"] == -1
    assert result["musical_accuracy"] == "not_evaluated"
    assert result["human_reviewed"] is False
    assert result["xml_export"] == "not_attempted"
    assert result["source_pdf_sha256"] == "a" * 64
    assert result["page_image_sha256"] == "b" * 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("page_number", 2),
        ("dpi", 150),
        ("source_pdf", "different.pdf"),
        ("source_pdf_sha256", "c" * 64),
        ("page_image_sha256", "d" * 64),
        ("page_image_size", [481, 215]),
        ("format_version", 1),
        ("status", "processing_failed"),
        ("experimental_adaptive_secondary", False),
        ("musical_accuracy", 0.95),
        ("xml_export", "completed"),
        ("predicted_events", 5),
        ("resolved_duration_events", True),
    ],
)
def test_rejects_incompatible_or_unverifiable_reports(field, value):
    adaptive = _probe(True)
    adaptive[field] = value
    with pytest.raises(ValueError):
        compare_probe_reports(_probe(False), adaptive)


def test_comparison_is_no_overwrite_and_reproducible(tmp_path):
    ordinary = tmp_path / "ordinary.json"
    adaptive = tmp_path / "adaptive.json"
    output = tmp_path / "comparison.json"
    ordinary.write_text(json.dumps(_probe(False)), encoding="utf-8")
    adaptive.write_text(json.dumps(_probe(True)), encoding="utf-8")
    expected = compare_probe_reports(_probe(False), _probe(True))
    assert compare_files(ordinary, adaptive, output) == expected
    assert json.loads(output.read_text(encoding="utf-8")) == expected
    with pytest.raises(FileExistsError):
        compare_files(ordinary, adaptive, output)


def test_invalid_uncertainty_counts_rejected():
    adaptive = _probe(True)
    adaptive["unresolved_duration_diagnostic_counts"] = {
        "secondary_stripe_ambiguous": -1
    }
    with pytest.raises(ValueError, match="diagnósticos"):
        compare_probe_reports(_probe(False), adaptive)

@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("source_pdf_sha256", None),
        ("source_pdf_sha256", "not-a-hash"),
        ("page_image_sha256", "A" * 64),
        ("page_image_size", [0, 215]),
        ("page_image_size", [480, True]),
        ("page_image_size", "480x215"),
    ],
)
def test_rejects_missing_or_malformed_image_provenance(field, invalid):
    baseline = _probe(False)
    adaptive = _probe(True)
    baseline[field] = invalid
    adaptive[field] = invalid
    with pytest.raises(ValueError):
        compare_probe_reports(baseline, adaptive)
