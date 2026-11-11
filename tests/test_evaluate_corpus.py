"""Verifica que o corpus não contamine treino/validação/teste entre manifestos."""

import json
import subprocess
import sys

import pytest

from tools.benchmark_integrity import BenchmarkIntegrityError
from tools.evaluate_corpus import evaluate_corpus


def _manifest(tmp_path, name, identifier, split, work_id="work-one"):
    path = tmp_path / name
    example = {
        "id": identifier,
        "work_id": work_id,
        "split": split,
        "image": "absent.png",
        "reference": None,
        "reference_status": "missing",
        "origin": "own_exercise",
        "configured": {"measure_left": 10, "measure_right": 100},
    }
    if work_id is None:
        example.pop("work_id")
    path.write_text(
        json.dumps({"format_version": 1, "examples": [example]}),
        encoding="utf-8",
    )
    return path


def test_preflight_rejects_same_work_in_different_splits_before_image_io(tmp_path):
    development = _manifest(tmp_path, "dev.json", "image-a", "development")
    validation = _manifest(tmp_path, "val.json", "image-b", "validation")
    with pytest.raises(BenchmarkIntegrityError, match="vazamento entre splits"):
        evaluate_corpus([development, validation])


def test_default_evaluates_only_development_and_preserves_failures(tmp_path):
    development = _manifest(tmp_path, "dev.json", "image-a", "development")
    reserved = _manifest(
        tmp_path, "reserved.json", "image-b", "test", work_id="other-work"
    )
    result = evaluate_corpus([development, reserved])
    assert result["integrity"]["example_count"] == 2
    assert result["selected_splits"] == ["development"]
    assert [row["id"] for row in result["images"]] == ["image-a"]
    assert result["summary"]["processing_failures"] == 1
    assert result["summary"]["reference_quality"]["missing"]["images"] == 1
    assert result["by_split"]["development"]["images"] == 1
    assert "test" not in result["by_split"]
    assert result["images"][0]["evaluation"] == "not_evaluated"


def test_test_split_requires_explicit_opt_in(tmp_path):
    test = _manifest(tmp_path, "test.json", "image-test", "test")
    with pytest.raises(ValueError, match="nenhum exemplo"):
        evaluate_corpus([test])
    result = evaluate_corpus([test], splits={"test"})
    assert result["selected_splits"] == ["test"]
    assert result["by_split"]["test"]["images"] == 1


def test_final_corpus_requires_explicit_work_id(tmp_path):
    legacy = _manifest(tmp_path, "legacy.json", "image-a", "development", None)
    with pytest.raises(BenchmarkIntegrityError, match="work_id explícito"):
        evaluate_corpus([legacy])
    result = evaluate_corpus([legacy], require_explicit_work_id=False)
    assert result["integrity"]["work_count"] == 1


def test_cli_writes_failed_batch_and_never_overwrites_report(tmp_path):
    manifest = _manifest(tmp_path, "manifest.json", "image-a", "development")
    report = tmp_path / "result.json"
    cmd = [
        sys.executable,
        "-m",
        "tools.evaluate_corpus",
        "--manifest",
        str(manifest),
        "--report",
        str(report),
    ]
    first = subprocess.run(cmd, capture_output=True, text=True)
    assert first.returncode == 1, first.stderr
    output = json.loads(report.read_text())
    assert output["summary"]["processing_failures"] == 1
    assert output["summary"]["complete_matches"] == 0
    saved = report.read_bytes()
    second = subprocess.run(cmd, capture_output=True, text=True)
    assert second.returncode == 2
    assert report.read_bytes() == saved
