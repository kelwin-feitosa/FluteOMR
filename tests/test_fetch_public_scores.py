"""Acquisition controls: no real network and no third-party fixtures in pytest."""

import hashlib
import io
import json

import pytest

from tools.fetch_public_scores import CorpusSourceError, download_score, load_catalog


PDF_URL = (
    "https://www.mutopiaproject.org/ftp/BachJS/BWV1013/"
    "bwv1013/bwv1013-a4.pdf"
)


class FakeResponse(io.BytesIO):
    def __init__(self, content, url=PDF_URL):
        super().__init__(content)
        self.url = url
        self.headers = {"Content-Length": str(len(content))}

    def geturl(self):
        return self.url


def _item(digest=None):
    return {
        "id": "mutopia-bwv1013",
        "work_id": "bachjs-bwv1013-edition",
        "license": "Public Domain dedication by typesetter (declared)",
        "source_category": "published_digitally_engraved_score",
        "rights_evidence_url": "https://www.mutopiaproject.org/some-license",
        "pdf_url": PDF_URL,
        "pdf_sha256": digest,
    }


def _pdf():
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def test_acquires_valid_pdf_and_records_actual_hash_without_claiming_pin(tmp_path):
    pdf = _pdf()
    requests = []

    def opener(request, *, timeout):
        requests.append((request.full_url, timeout))
        return FakeResponse(pdf)

    record = download_score(_item(), tmp_path, opener=opener)
    base = tmp_path / "mutopia-bwv1013"
    assert (base / "source.pdf").read_bytes() == pdf
    assert json.loads((base / "acquisition.json").read_text()) == record
    assert record["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert record["checksum_verified_against_pin"] is False
    assert record["human_review_status"] == "not_reviewed"
    assert requests == [(PDF_URL, 30)]
    assert not list(base.glob(".incoming-*"))
    before = (base / "source.pdf").read_bytes()
    with pytest.raises(FileExistsError):
        download_score(_item(), tmp_path, opener=opener)
    assert (base / "source.pdf").read_bytes() == before


def test_pinned_sha256_is_verified_before_writing(tmp_path):
    pdf = _pdf()
    item = _item(hashlib.sha256(pdf).hexdigest())
    record = download_score(item, tmp_path, opener=lambda *_a, **_k: FakeResponse(pdf))
    assert record["checksum_verified_against_pin"] is True


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"<html>HTML instead of PDF</html>", "PDF completo"),
        (b"%PDF-1.4\nmissing trailer", "PDF completo"),
    ],
)
def test_invalid_remote_payload_is_rejected_without_partial_files(
    tmp_path, payload, message
):
    with pytest.raises(CorpusSourceError, match=message):
        download_score(
            _item(), tmp_path, opener=lambda *_a, **_k: FakeResponse(payload)
        )
    folder = tmp_path / "mutopia-bwv1013"
    assert not (folder / "source.pdf").exists()
    assert not (folder / "acquisition.json").exists()
    assert not list(folder.glob(".incoming-*"))


def test_wrong_sha256_is_rejected_without_partial_files(tmp_path):
    with pytest.raises(CorpusSourceError, match="hash"):
        download_score(
            _item("a" * 64),
            tmp_path,
            opener=lambda *_a, **_k: FakeResponse(_pdf()),
        )
    assert not (tmp_path / "mutopia-bwv1013/source.pdf").exists()


def test_redirect_to_untrusted_host_is_rejected(tmp_path):
    with pytest.raises(CorpusSourceError, match="aprovados"):
        download_score(
            _item(),
            tmp_path,
            opener=lambda *_a, **_k: FakeResponse(
                _pdf(), url="https://evil.example/download.pdf"
            ),
        )
    assert not (tmp_path / "mutopia-bwv1013/source.pdf").exists()


def test_too_large_content_length_is_rejected_before_streaming(tmp_path):
    def opener(*_a, **_k):
        response = FakeResponse(_pdf())
        response.headers["Content-Length"] = str(21 * 1024 * 1024)
        return response

    with pytest.raises(CorpusSourceError, match="Content-Length"):
        download_score(_item(), tmp_path, opener=opener)


def test_catalog_rejects_unsafe_source_even_without_network(tmp_path):
    bad = _item()
    bad["pdf_url"] = "http://127.0.0.1/payload.pdf"
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"format_version": 1, "sources": [bad]}))
    with pytest.raises(CorpusSourceError, match="hosts aprovados"):
        load_catalog(path)


def test_catalog_valid_and_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "sources.json"
    data = {"format_version": 1, "sources": [_item()]}
    path.write_text(json.dumps(data))
    assert load_catalog(path)["mutopia-bwv1013"]["pdf_sha256"] is None
    data["sources"].append(_item())
    path.write_text(json.dumps(data))
    with pytest.raises(CorpusSourceError, match="id duplicado"):
        load_catalog(path)
