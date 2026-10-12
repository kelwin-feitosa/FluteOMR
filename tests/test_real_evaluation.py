"""Avaliador com dados temporários, sem partituras privadas no CI."""

import json
import subprocess
import sys

import pytest

from tools.evaluate_real_staffs import evaluate
from tools.staff_examples import make_staff_image


def test_evaluator_counts_and_writes_debug_images(tmp_path):
    image, _ = make_staff_image()
    image.save(tmp_path / "synthetic.png")
    manifest = tmp_path / "counts.json"
    manifest.write_text('{"synthetic.png": 1}')
    rows, failures = evaluate(tmp_path, manifest, tmp_path / "debug")
    assert rows == [("synthetic.png", 1, 1)]
    assert failures == []
    assert (tmp_path / "debug/synthetic-debug.png").is_file()


@pytest.mark.parametrize("expected,code", [(2, 1), (1, 0)])
def test_validate_exit_code_for_count_mismatch(tmp_path, expected, code):
    image, _ = make_staff_image()
    image.save(tmp_path / "synthetic.png")
    manifest = tmp_path / "counts.json"
    manifest.write_text(json.dumps({"synthetic.png": expected}))
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.evaluate_real_staffs",
            "--images-dir",
            str(tmp_path),
            "--manifest",
            str(manifest),
            "--validate",
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == code
    assert f"expected={expected} detected=1" in run.stdout


def test_missing_file_is_reported_and_fails_validation(tmp_path):
    manifest = tmp_path / "counts.json"
    manifest.write_text('{"missing.png": 1}')
    rows, failures = evaluate(tmp_path, manifest)
    assert rows == [("missing.png", 1, None)]
    assert failures == ["missing.png: arquivo ausente"]
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.evaluate_real_staffs",
            "--images-dir",
            str(tmp_path),
            "--manifest",
            str(manifest),
            "--validate",
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 2
    assert "detected=None" in run.stdout
    assert "evaluated=0/1" in run.stdout
    assert "difference=unknown" in run.stdout


def test_manifest_cannot_escape_image_directory(tmp_path):
    manifest = tmp_path / "counts.json"
    manifest.write_text('{"../secret.png": 1}')
    with pytest.raises(ValueError, match="Manifesto inválido"):
        evaluate(tmp_path, manifest)
