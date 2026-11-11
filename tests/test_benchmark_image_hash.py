"""Proteção contra vazamento de imagens byte-idênticas no corpus."""

import json

import pytest

from tools.benchmark_integrity import BenchmarkIntegrityError, validate_manifests


def _manifest(folder, name, identifier, work, split, digest=None):
    example = {
        "id": identifier,
        "work_id": work,
        "split": split,
        "image": "not-opened.png",
        "origin": "local",
        "reference_status": "missing",
    }
    if digest is not None:
        example["image_sha256"] = digest
    path = folder / name
    path.write_text(
        json.dumps({"format_version": 1, "examples": [example]}),
        encoding="utf-8",
    )
    return path


def test_same_image_in_different_splits_is_rejected_even_with_different_work_ids(
    tmp_path,
):
    a = _manifest(tmp_path, "dev.json", "a", "work-a", "development", "a" * 64)
    b = _manifest(tmp_path, "test.json", "b", "work-b", "test", "A" * 64)
    with pytest.raises(BenchmarkIntegrityError, match="vazamento de imagem"):
        validate_manifests([a, b], require_explicit_work_id=True)


def test_same_image_cannot_claim_two_distinct_works_in_same_split(tmp_path):
    a = _manifest(tmp_path, "a.json", "a", "work-a", "development", "b" * 64)
    b = _manifest(tmp_path, "b.json", "b", "work-b", "development", "b" * 64)
    with pytest.raises(BenchmarkIntegrityError, match="obras distintas"):
        validate_manifests([a, b])


def test_same_work_same_split_can_have_duplicate_hash_with_clear_metadata(tmp_path):
    a = _manifest(tmp_path, "a.json", "a", "same-work", "development", "c" * 64)
    b = _manifest(tmp_path, "b.json", "b", "same-work", "development", "C" * 64)
    report = validate_manifests([a, b], require_explicit_work_id=True)
    assert report["work_count"] == 1
    assert report["image_hash_entries"] == 2
    assert report["image_hash_coverage"] == {"provided": 2, "total": 2}


@pytest.mark.parametrize("invalid", ["", "a" * 63, "g" * 64, "0x" + "a" * 64])
def test_invalid_hash_is_rejected_before_reading_images(tmp_path, invalid):
    p = _manifest(tmp_path, "bad.json", "a", "work-a", "development", invalid)
    with pytest.raises(BenchmarkIntegrityError, match="image_sha256"):
        validate_manifests([p])


def test_legacy_data_without_declared_hash_is_still_supported(tmp_path):
    p = _manifest(tmp_path, "legacy.json", "a", "work-a", "development")
    report = validate_manifests([p])
    assert report["image_hash_entries"] == 0
    assert report["image_hash_coverage"] == {"provided": 0, "total": 1}
