"""Baseline geométrico sobre PDF de partitura publicada, sem ground truth musical.

Cada página é rasterizada separadamente; as notas não são pontuadas.
"""

import argparse
import json
from pathlib import Path
from time import perf_counter

from PIL import ImageDraw

from fluteomr.pdf_io import load_pdf_page, pdf_page_count
from fluteomr.staff_detection import detect_staffs


def _preview(image, detection, target: Path) -> None:
    """Desenha a evidência na imagem e reduz a escala somente para visualização."""
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    for index, staff in enumerate(detection.staffs, 1):
        region = staff.region
        draw.rectangle(
            (region.left, region.top, region.right, region.bottom),
            outline="red",
            width=3,
        )
        draw.text((region.left, max(0, region.top - 16)), str(index), fill="blue")
    overlay.thumbnail((1200, 1600))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        overlay.save(stream, format="PNG")


def benchmark_pdf_staffs(
    source: Path,
    *,
    page_numbers: list[int],
    resolutions: list[int],
    report: Path | None = None,
    preview_dir: Path | None = None,
) -> dict:
    count = pdf_page_count(source)
    if not page_numbers or len(set(page_numbers)) != len(page_numbers):
        raise ValueError("páginas precisam ser únicas e não vazias")
    if not resolutions or len(set(resolutions)) != len(resolutions):
        raise ValueError("DPIs precisam ser únicos e não vazios")
    if any(type(p) is not int or not 1 <= p <= count for p in page_numbers):
        raise ValueError("página fora dos limites do PDF")
    if any(type(d) is not int or not 72 <= d <= 400 for d in resolutions):
        raise ValueError("DPI inválido (72–400)")
    if report is not None and report.exists():
        raise FileExistsError("relatório já existe")
    if preview_dir is not None and any(
        (preview_dir / f"page-{p}-dpi-{d}.png").exists()
        for p in page_numbers
        for d in resolutions
    ):
        raise FileExistsError("visualização já existe")

    samples = []
    for p in page_numbers:
        for dpi in resolutions:
            started = perf_counter()
            image = load_pdf_page(source, page_number=p, dpi=dpi)
            raster_seconds = perf_counter() - started
            started = perf_counter()
            detection = detect_staffs(image)
            detect_seconds = perf_counter() - started
            samples.append(
                {
                    "page_number": p,
                    "dpi": dpi,
                    "image_size": list(image.size),
                    "status": detection.status,
                    "staff_count_detected": detection.staff_count,
                    "candidate_line_count": len(detection.candidates),
                    "staff_line_y": [
                        [round(line.y, 2) for line in staff.lines]
                        for staff in detection.staffs
                    ],
                    "staff_spacings": [
                        round(staff.spacing, 3) for staff in detection.staffs
                    ],
                    "diagnostics": list(detection.diagnostics),
                    "raster_seconds": round(raster_seconds, 4),
                    "detection_seconds": round(detect_seconds, 4),
                    "reference_staff_count": None,
                    "staff_accuracy": "not_evaluated",
                    "musical_event_accuracy": "not_evaluated",
                }
            )
            if preview_dir is not None:
                _preview(image, detection, preview_dir / f"page-{p}-dpi-{dpi}.png")

    result = {
        "format_version": 1,
        "evaluation_scope": "staff_geometry_only",
        "source_pdf": source.name,
        "total_pdf_pages": count,
        "pages_evaluated": page_numbers,
        "dpis_evaluated": resolutions,
        "samples": samples,
        "accuracy_caveat": (
            "Contagens detectadas não são acertos medidos sem contagens de "
            "referência independentes; nem representam precisão de notas."
        ),
    }
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", action="append", type=int, required=True)
    parser.add_argument("--dpi", action="append", type=int, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path)
    args = parser.parse_args()
    try:
        result = benchmark_pdf_staffs(
            args.pdf,
            page_numbers=args.page,
            resolutions=args.dpi,
            report=args.report,
            preview_dir=args.preview_dir,
        )
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
