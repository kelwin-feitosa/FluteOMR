"""Extrai uma página PDF para anotação musical, preservando proveniência.

Não realiza OMR nem confirma a exatidão musical de referências.
"""

import argparse
import hashlib
import json
from pathlib import Path

from fluteomr.pdf_io import load_pdf_page, pdf_page_count


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def extract_pdf_page(
    source: Path,
    output: Path,
    metadata: Path,
    *,
    page_number: int = 1,
    dpi: int = 200,
    source_url: str | None = None,
    license_id: str | None = None,
) -> dict:
    """Salva PNG e JSON novos; nunca interpreta ou redistribui o PDF original."""
    if len({source.resolve(), output.resolve(), metadata.resolve()}) != 3:
        raise ValueError("PDF, PNG e JSON devem ter caminhos distintos")
    if output.exists() or metadata.exists():
        raise FileExistsError("arquivo de saída já existe; escolha caminhos novos")
    count = pdf_page_count(source)
    image = load_pdf_page(source, page_number=page_number, dpi=dpi)
    data = {
        "format_version": 1,
        "source": {
            "filename": source.name,
            "sha256": _digest(source),
            "page_count": count,
            "page_number": page_number,
            "dpi": dpi,
            "source_url": source_url,
            "license_id": license_id,
            "license_status": "user_declared_unverified",
        },
        "image": {
            "filename": output.name,
            "format": "PNG",
            "width": image.width,
            "height": image.height,
            "sha256": None,
        },
        "coordinate_frame": "pdf_page_raster_pixels",
        "reference_status": "missing_human_review",
        "warning": (
            "PDF rasterizado não é MusicXML validado. Conferir direitos, "
            "referência musical e correção da transcrição separadamente."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        image.save(stream, format="PNG")
    try:
        data["image"]["sha256"] = _digest(output)
        with metadata.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    except BaseException:
        # Remove apenas o PNG recém-gerado; não toca em arquivos preexistentes.
        output.unlink(missing_ok=True)
        raise
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page-number", type=int, default=1)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--source-url")
    parser.add_argument("--license-id")
    args = parser.parse_args()
    try:
        result = extract_pdf_page(
            args.pdf,
            args.output,
            args.metadata,
            page_number=args.page_number,
            dpi=args.dpi,
            source_url=args.source_url,
            license_id=args.license_id,
        )
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
