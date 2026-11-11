"""Novo pacote humano preserva hash da imagem também no manifesto."""

import hashlib
import json

import pytest
from PIL import Image

from fluteomr.music_review import prepare_review, verify_review
from tools.benchmark_integrity import BenchmarkIntegrityError, validate_manifests


def _package(tmp_path, folder, work):
    source = tmp_path / "source.png"
    if not source.exists():
        Image.new("RGB", (120, 80), "white").save(source)
    return prepare_review(
        source,
        tmp_path / folder,
        example_id=folder,
        work_id=work,
        crop=(0, 0, 120, 80),
        scale=1,
        reference=None,
        measures=(1,),
        staff_id=None,
        system_id=None,
        configured={"measure_left": 0, "measure_right": 119},
    )


def test_new_review_bundle_has_verifiable_image_hash(tmp_path):
    manifest = _package(tmp_path, "one", "work-one")
    example = json.loads(manifest.read_text())["examples"][0]
    actual = hashlib.sha256((manifest.parent / "image.png").read_bytes()).hexdigest()
    assert example["image_sha256"] == actual
    assert verify_review(manifest, example)["status"] == "draft"
    integrity = validate_manifests([manifest], require_explicit_work_id=True)
    assert integrity["image_hash_entries"] == 1


def test_review_rejects_manifest_hash_replacement(tmp_path):
    manifest = _package(tmp_path, "one", "work-one")
    data = json.loads(manifest.read_text())
    data["examples"][0]["image_sha256"] = "0" * 64
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="hash da imagem divergente"):
        verify_review(manifest, data["examples"][0])


def test_review_packages_with_same_image_cannot_cross_splits(tmp_path):
    a = _package(tmp_path, "one", "work-one")
    b = _package(tmp_path, "two", "work-two")
    data = json.loads(b.read_text())
    data["examples"][0]["split"] = "validation"
    b.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BenchmarkIntegrityError, match="vazamento de imagem"):
        validate_manifests([a, b], require_explicit_work_id=True)
