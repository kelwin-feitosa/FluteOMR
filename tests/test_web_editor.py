"""Avaliação do editor web com arquivos controlados e sem dados privados."""

import json
import shutil
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from PIL import Image

from fluteomr.annotations import image_sha256
from fluteomr.corrections import (
    CorrectionError,
    PageCatalog,
    RevisionConflict,
)
from tools.web_editor import EditorServer


def _fixture(tmp_path):
    images = tmp_path / "images"
    suggestions = tmp_path / "suggestions"
    corrections = tmp_path / "corrections"
    images.mkdir()
    suggestions.mkdir()
    image_path = images / "score.png"
    Image.new("RGB", (200, 160), "white").save(image_path)
    proposal = {
        "schema_version": 1,
        "kind": "suggestions_not_ground_truth",
        "image": {
            "id": "score",
            "filename": "score.png",
            "sha256": image_sha256(image_path),
            "width": 200,
            "height": 160,
        },
        "detections": {
            "staffs": [
                {"region": {"left": 15, "top": 25, "right": 180, "bottom": 65}},
                {"region": {"left": 15, "top": 100, "right": 180, "bottom": 140}},
            ],
            "systems": {"status": "ambiguous", "groups": [[0], [1]], "diagnostics": []},
            "clefs": [
                {
                    "status": "detected",
                    "region": {"left": 20, "top": 15, "right": 37, "bottom": 75},
                    "diagnostics": [],
                },
                {
                    "status": "inconclusive",
                    "region": None,
                    "diagnostics": ["multiple_plausible_components"],
                },
            ],
        },
    }
    source = suggestions / "score.png.suggestions.json"
    source.write_text(json.dumps(proposal), encoding="utf-8")
    reference = tmp_path / "validated.reference.json"
    reference.write_text('{"human":"unchanged"}', encoding="utf-8")
    catalog = PageCatalog(images, suggestions, corrections)
    return catalog, source, reference, image_path


def test_visual_state_keeps_automatic_and_corrected_layers_distinct(tmp_path):
    catalog, source, reference, image = _fixture(tmp_path)
    page_id = catalog.pages()[0]["id"]
    assert catalog.pages()[0] == {
        "id": page_id,
        "name": "score.png",
        "staff_count": 2,
        "pending_count": 1,
        "corrected_count": 0,
    }
    page = catalog.page(page_id)
    assert page["view"]["counts"] == {
        "staffs": 2,
        "automatic_detected": 1,
        "pending": 1,
        "corrected": 0,
    }
    assert page["view"]["clefs"][0]["effective"]["source"] == "automatic_prediction"
    assert page["view"]["clefs"][1]["effective"]["state"] == "unknown"
    before = (source.read_bytes(), reference.read_bytes(), image.read_bytes())
    decision = {
        "state": "present",
        "kind": "treble",
        "region": {"left": 21, "top": 89, "right": 39, "bottom": 150},
    }
    saved = catalog.save(page_id, {"base_revision": 0, "decisions": {"s1": decision}})
    assert saved["revision"] == 1
    assert saved["view"]["counts"] == {
        "staffs": 2,
        "automatic_detected": 1,
        "pending": 0,
        "corrected": 1,
    }
    assert saved["view"]["clefs"][0]["effective"]["source"] == "automatic_prediction"
    assert saved["view"]["clefs"][1]["effective"]["source"] == "user_correction"
    assert catalog.pages()[0]["pending_count"] == 0
    assert catalog.pages()[0]["corrected_count"] == 1
    reopened = PageCatalog(
        catalog.images_dir, catalog.suggestions_dir, catalog.corrections_dir
    )
    assert reopened.page(page_id)["decisions"] == {"s1": decision}
    assert (source.read_bytes(), reference.read_bytes(), image.read_bytes()) == before
    with pytest.raises(RevisionConflict):
        catalog.save(page_id, {"base_revision": 0, "decisions": {}})


def test_invalid_decisions_and_source_mismatch(tmp_path):
    catalog, source, _, image = _fixture(tmp_path)
    page_id = catalog.pages()[0]["id"]
    for decisions in (
        {"s99": {"state": "absent", "kind": None, "region": None}},
        {"s0": {"state": "present", "kind": "treble", "region": None}},
        {
            "s0": {
                "state": "present",
                "kind": "bass",
                "region": {"left": 0, "top": 0, "right": 300, "bottom": 20},
            }
        },
        {"s0": {"state": "absent", "kind": "treble", "region": None}},
        {
            "s0": {
                "state": "present",
                "kind": "treble",
                "region": {"left": True, "top": 0, "right": 5, "bottom": 10},
            }
        },
    ):
        with pytest.raises(CorrectionError):
            catalog.save(page_id, {"base_revision": 0, "decisions": decisions})
    assert not catalog.corrections_dir.exists()
    original = image.read_bytes()
    image.write_bytes(original + b"extra")
    with pytest.raises(CorrectionError, match="hash da imagem"):
        catalog.page(page_id)
    image.write_bytes(original)
    source.write_text(source.read_text() + " ", encoding="utf-8")
    with pytest.raises(CorrectionError, match="sugestões mudaram"):
        catalog.page(page_id)


def test_absent_is_not_unknown_and_automatic_prediction_can_be_corrected(tmp_path):
    catalog, _, _, _ = _fixture(tmp_path)
    page_id = catalog.pages()[0]["id"]
    result = catalog.save(
        page_id,
        {
            "base_revision": 0,
            "decisions": {
                "s0": {
                    "state": "present",
                    "kind": "bass",
                    "region": {"left": 20, "top": 15, "right": 37, "bottom": 75},
                },
                "s1": {"state": "absent", "kind": None, "region": None},
            },
        },
    )
    assert result["view"]["counts"]["pending"] == 0
    assert result["view"]["clefs"][0]["prediction"]["status"] == "detected"
    assert result["view"]["clefs"][0]["effective"]["kind"] == "bass"
    assert result["view"]["clefs"][1]["effective"]["state"] == "absent"


@contextmanager
def _running(catalog):
    server = EditorServer(("127.0.0.1", 0), catalog)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request(url, method="GET", payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=data, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=5) as response:
            body = response.read()
            return response.status, body, response.headers
    except HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def test_http_api_read_write_guards_and_file_allowlist(tmp_path):
    catalog, source, reference, image = _fixture(tmp_path)
    old_bytes = (source.read_bytes(), reference.read_bytes(), image.read_bytes())
    page_id = catalog.pages()[0]["id"]
    with _running(catalog) as (server, base):
        status, body, _ = _request(base + "/api/bootstrap")
        assert status == 200
        bootstrap = json.loads(body)
        assert bootstrap["pages"][0]["id"] == page_id
        assert bootstrap["pages"][0]["pending_count"] == 1
        status, body, _ = _request(base + "/")
        assert status == 200
        assert b'id="home-screen"' in body
        assert b'id="back-home"' in body
        status, body, _ = _request(base + f"/api/pages/{page_id}")
        assert status == 200 and json.loads(body)["view"]["counts"]["pending"] == 1
        status, body, headers = _request(base + f"/api/pages/{page_id}/image")
        assert status == 200 and body == image.read_bytes()
        assert headers["Content-Type"] == "image/png"
        for path in (
            "/api/pages/../../etc/passwd",
            "/api/pages/invalid/image",
            "/private.json",
        ):
            assert _request(base + path)[0] == 404
        assert _request(base + "/app.js")[0] == 200
        assert _request(base + "/geometry.js")[0] == 200
        assert _request(base + "/", headers={"Host": "attacker.example"})[0] == 403
        payload = {
            "base_revision": 0,
            "decisions": {"s1": {"state": "absent", "kind": None, "region": None}},
        }
        endpoint = base + f"/api/pages/{page_id}/corrections"
        headers = {
            "Content-Type": "application/json",
            "X-FluteOMR-Token": bootstrap["token"],
        }
        assert _request(endpoint, "PUT", payload, headers)[0] == 403
        assert (
            _request(
                endpoint, "PUT", payload, {**headers, "Origin": "http://evil.test"}
            )[0]
            == 403
        )
        assert (
            _request(
                endpoint,
                "PUT",
                payload,
                {**headers, "Origin": base, "X-FluteOMR-Token": "wrong"},
            )[0]
            == 403
        )
        assert (
            _request(endpoint, "POST", payload, {**headers, "Origin": base})[0] == 405
        )
        assert _request(endpoint, "PUT", payload, {**headers, "Origin": base})[0] == 200
        status, body, _ = _request(base + "/api/bootstrap")
        assert status == 200
        assert json.loads(body)["pages"][0]["pending_count"] == 0
        assert json.loads(body)["pages"][0]["corrected_count"] == 1
        assert _request(endpoint, "PUT", payload, {**headers, "Origin": base})[0] == 409
        assert server.server_address[0] == "127.0.0.1"
    assert (
        source.read_bytes(),
        reference.read_bytes(),
        image.read_bytes(),
    ) == old_bytes


def test_geometry_transform_in_browser_code():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node não instalado para verificar JS puro")
    script = Path(__file__).resolve().parents[1] / "tools/web_static/geometry.js"
    code = (
        "const assert=require('node:assert/strict');"
        "const g=require(process.argv[1]);"
        "for(const z of [0.25,0.7,1,1.8,3]){"
        "const b={left:30,top:40,right:50,bottom:80};"
        "const s=g.boxStyle(b,z);"
        "assert.equal(s.width,21*z);"
        "const p=g.screenToImage(100+30*z,200+40*z,100,200,z,200,160);"
        "assert.deepEqual(p,{x:30,y:40});}"
        "assert.deepEqual(g.screenToImage(-50,999,100,200,2,200,160),{x:0,y:159});"
    )
    subprocess.run([node, "-e", code, str(script)], check=True)


def test_real_fairy_counts_when_local_data_available():
    base = Path(__file__).resolve().parents[1] / "outputs/novas-partituras"
    if not (base / "png").is_dir() or not (base / "suggestions").is_dir():
        pytest.skip("partituras locais não fazem parte do CI")
    catalog = PageCatalog(
        base / "png", base / "suggestions", base / "_unused_test_corrections"
    )
    fairy = next(
        page for page in catalog.pages() if "Fairy_Tail_Main_Theme" in page["name"]
    )
    page = catalog.page(fairy["id"])
    assert page["view"]["counts"]["staffs"] == 7
    assert page["view"]["counts"]["automatic_detected"] == 6
    assert page["view"]["counts"]["pending"] == 1
    assert page["view"]["clefs"][1]["prediction"]["region"] is None
