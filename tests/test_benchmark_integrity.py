"""Separação por obra, não por imagem, evita vazamento de benchmarks."""

import json
from pathlib import Path

import pytest

from tools.benchmark_integrity import (
    BenchmarkIntegrityError,
    validate_examples,
    validate_manifests,
)
from tools.evaluate_music import evaluate_manifest


def _write(tmp_path: Path, name: str, examples: list[dict]) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps({"format_version": 1, "examples": examples}), encoding="utf-8"
    )
    return path


def _example(identifier: str, split: str, work_id: str | None = "same-work"):
    data = {
        "id": identifier,
        "split": split,
        "image": "not-opened.png",
        "reference_status": "missing",
        "origin": "own_exercise",
        "configured": {"measure_left": 10, "measure_right": 90},
    }
    if work_id is not None:
        data["work_id"] = work_id
    return data


def test_variants_in_same_split_are_valid_across_manifests(tmp_path):
    a = _write(tmp_path, "a.json", [_example("font-a", "development")])
    b = _write(tmp_path, "b.json", [_example("font-b", "development")])
    report = validate_manifests([a, b], require_explicit_work_id=True)
    assert report["status"] == "metadata_consistent"
    assert report["example_count"] == 2
    assert report["work_count"] == 1
    assert report["by_split"]["development"] == {"examples": 2, "works": 1}
    assert report["by_split"]["validation"] == {"examples": 0, "works": 0}


def test_same_work_in_different_splits_is_rejected_across_manifests(tmp_path):
    development = _write(tmp_path, "dev.json", [_example("font-a", "development")])
    validation = _write(tmp_path, "val.json", [_example("font-b", "validation")])
    with pytest.raises(BenchmarkIntegrityError, match="vazamento entre splits"):
        validate_manifests([development, validation])


def test_duplicate_example_id_is_rejected_even_with_distinct_work_id(tmp_path):
    first = _write(tmp_path, "one.json", [_example("dup", "development", "a")])
    second = _write(tmp_path, "two.json", [_example("dup", "development", "b")])
    with pytest.raises(BenchmarkIntegrityError, match="id duplicado"):
        validate_manifests([first, second])


def test_final_corpus_can_require_explicit_work_ids(tmp_path):
    manifest = _write(
        tmp_path, "legacy.json", [_example("single", "development", None)]
    )
    assert validate_manifests([manifest])["work_count"] == 1
    with pytest.raises(BenchmarkIntegrityError, match="work_id explícito"):
        validate_manifests([manifest], require_explicit_work_id=True)


@pytest.mark.parametrize(
    "invalid",
    [
        [None],
        [{"id": "", "split": "development"}],
        [{"id": "x", "split": "invalid"}],
        [{"id": "x", "split": ["development"]}],
        [{"id": "x", "split": "development", "work_id": []}],
    ],
)
def test_invalid_metadata_fails_with_specific_validation_error(invalid):
    with pytest.raises(BenchmarkIntegrityError):
        validate_examples(invalid, source="invalid-manifest")


def test_evaluator_rejects_leakage_before_opening_images(tmp_path):
    manifest = _write(
        tmp_path,
        "mixed.json",
        [_example("a", "development"), _example("b", "test")],
    )
    with pytest.raises(BenchmarkIntegrityError, match="vazamento entre splits"):
        evaluate_manifest(manifest, tmp_path, continue_on_error=True)


def test_existing_source_authored_benchmark_manifests_do_not_mix_works():
    root = Path(__file__).parent / "data/music_lab"
    paths = [
        root / "sprint1d/development-manifest.json",
        root / "sprint1d/validation-manifest.json",
    ]
    report = validate_manifests(paths, require_explicit_work_id=True)
    assert report["by_split"]["development"]["works"] == 2
    assert report["by_split"]["validation"]["works"] == 1
