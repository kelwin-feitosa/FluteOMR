"""PDFs vetoriais gerados no próprio teste, sem dados de terceiros."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from fluteomr.image_io import MAX_PIXELS
from tools.extract_pdf_page import extract_pdf_page
from fluteomr.pdf_io import PdfInputError, load_pdf_page, pdf_page_count


def _make_pdf(path: Path, contents: list[str], *, size=(400, 200)) -> Path:
    """Escreve um PDF mínimo com xref válido sem usar outro motor OMR."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = b" ".join(f"{3 + 2 * i} 0 R".encode() for i in range(len(contents)))
    objects.append(
        b"<< /Type /Pages /Kids ["
        + kids
        + b"] /Count "
        + str(len(contents)).encode()
        + b" >>"
    )
    for index, command in enumerate(contents):
        page_id = 3 + 2 * index
        stream = command.encode("ascii")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
            + f"{size[0]} {size[1]}".encode()
            + b"] /Resources << >> /Contents "
            + f"{page_id + 1} 0 R".encode()
            + b" >>"
        )
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    startxref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{startxref}\n%%EOF\n".encode()
    )
    path.write_bytes(result)
    return path


STAFF = "0 0 0 RG 1 w " + " ".join(
    f"20 {y} m 380 {y} l S" for y in (70, 82, 94, 106, 118)
)


def test_pdf_counts_pages_and_renders_requested_page(tmp_path):
    pdf = _make_pdf(tmp_path / "score.pdf", ["", STAFF])
    assert pdf_page_count(pdf) == 2
    first = load_pdf_page(pdf, dpi=144)
    second = load_pdf_page(pdf, page_number=2, dpi=144)
    assert first.mode == second.mode == "RGB"
    assert first.size == second.size == (800, 400)
    assert first.getextrema() == ((255, 255),) * 3
    assert all(low == 0 and high == 255 for low, high in second.getextrema())


@pytest.mark.parametrize(
    ("page", "dpi"),
    [(0, 200), (True, 200), (3, 200), (1, 40), (1, 500), (1, True), (1, float("nan"))],
)
def test_invalid_selection_rejected(tmp_path, page, dpi):
    pdf = _make_pdf(tmp_path / "score.pdf", ["", STAFF])
    with pytest.raises(PdfInputError):
        load_pdf_page(pdf, page_number=page, dpi=dpi)


def test_corrupt_pdf_and_non_pdf_are_rejected(tmp_path):
    source = tmp_path / "fake.pdf"
    source.write_bytes(b"not a pdf")
    with pytest.raises(PdfInputError, match="cabeçalho"):
        load_pdf_page(source)
    source.write_bytes(b"%PDF-1.4\nnot a real PDF\n")
    with pytest.raises(PdfInputError, match="abrir"):
        load_pdf_page(source)


def test_huge_pdf_page_is_rejected_before_rendering(tmp_path):
    source = _make_pdf(tmp_path / "huge.pdf", [""], size=(10000, 10000))
    with pytest.raises(PdfInputError, match=str(MAX_PIXELS)):
        load_pdf_page(source, dpi=200)


def test_cli_accepts_pdf_and_keeps_partial_report_without_musicxml(tmp_path):
    source = _make_pdf(tmp_path / "score.pdf", ["", STAFF])
    report = tmp_path / "report.json"
    musicxml = tmp_path / "score.musicxml"
    command = [
        sys.executable,
        "-m",
        "tools.transcribe_page",
        str(source),
        "--layout",
        "solo",
        "--clef",
        "treble",
        "--time",
        "4/4",
        "--page-number",
        "2",
        "--dpi",
        "144",
        "--allow-clefless",
        "--report",
        str(report),
        "--output",
        str(musicxml),
    ]
    run = subprocess.run(command, capture_output=True, text=True)
    assert run.returncode == 1, run.stderr
    data = json.loads(report.read_text())
    assert data["page_number"] == 2
    assert data["source"]["format"] == "pdf"
    assert data["source"]["page_number"] == 2
    assert data["source"]["dpi"] == 144
    assert data["staff_results"]
    assert data["xml_export"] == "blocked_by_prediction_issues"
    assert not musicxml.exists()
    before = report.read_bytes()
    again = subprocess.run(command, capture_output=True, text=True)
    assert again.returncode == 2
    assert report.read_bytes() == before


def test_extract_pdf_page_records_provenance_without_claiming_human_review(tmp_path):
    import hashlib

    source = _make_pdf(tmp_path / "score.pdf", ["", STAFF])
    output = tmp_path / "staging/page-2.png"
    metadata = tmp_path / "staging/page-2.json"
    data = extract_pdf_page(
        source,
        output,
        metadata,
        page_number=2,
        dpi=144,
        source_url="https://example.org/score",
        license_id="CC0-1.0",
    )
    saved = json.loads(metadata.read_text())
    assert saved == data
    assert data["source"]["page_number"] == 2
    assert data["source"]["page_count"] == 2
    assert data["source"]["license_status"] == "user_declared_unverified"
    assert data["reference_status"] == "missing_human_review"
    assert data["image"]["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert data["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    with Image.open(output) as image:
        assert image.size == (800, 400)
        assert all(low == 0 and high == 255 for low, high in image.getextrema())
    original = output.read_bytes(), metadata.read_bytes()
    with pytest.raises(FileExistsError):
        extract_pdf_page(source, output, metadata, page_number=1)
    assert (output.read_bytes(), metadata.read_bytes()) == original


def test_extract_pdf_page_refuses_invalid_source_without_partial_outputs(tmp_path):
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"not a PDF")
    png = tmp_path / "out/page.png"
    metadata = tmp_path / "out/page.json"
    with pytest.raises(PdfInputError):
        extract_pdf_page(source, png, metadata)
    assert not png.exists() and not metadata.exists()


def test_extract_pdf_page_cli_exports_valid_png_and_metadata(tmp_path):
    source = _make_pdf(tmp_path / "score.pdf", [STAFF])
    png = tmp_path / "out.png"
    metadata = tmp_path / "out.json"
    cmd = [
        sys.executable,
        "-m",
        "tools.extract_pdf_page",
        str(source),
        "--page-number",
        "1",
        "--dpi",
        "144",
        "--output",
        str(png),
        "--metadata",
        str(metadata),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert png.is_file()
    assert json.loads(completed.stdout) == json.loads(metadata.read_text())
