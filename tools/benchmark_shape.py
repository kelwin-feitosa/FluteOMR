"""Comparação A/B exata de _shape com a nova soma por prefixos em PDF publicado.

Sem ground truth de notas, sem inferir percentuais musicais. Cronometragens
repetidas são somente um microbenchmark em um mesmo processo/runner.
"""

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from fluteomr.notes import (
    _horizontal_ink_prefix,
    _ink_without_staff,
    _offset_spans,
    _shape,
    _shape_from_prefix,
)
from fluteomr.pdf_io import load_pdf_page
from fluteomr.staff_detection import detect_staffs


def _masks(spacing: float):
    rx = max(3, round(0.65 * spacing))
    ry = max(2, round(0.42 * spacing))
    core = tuple(
        (dx, dy)
        for dy in range(-ry, ry + 1)
        for dx in range(-rx, rx + 1)
        if (dx / rx) ** 2 + (dy / ry) ** 2 <= 0.30
    )
    rim = tuple(
        (dx, dy)
        for dy in range(-ry, ry + 1)
        for dx in range(-rx, rx + 1)
        if 0.55 <= (dx / rx) ** 2 + (dy / ry) ** 2 <= 1.15
    )
    sides = tuple(
        tuple(
            (dx, dy)
            for dx, dy in rim
            if dx * side > 0 and abs(dx) >= 0.55 * rx and abs(dy) <= 0.6 * ry
        )
        for side in (-1, 1)
    )
    return rx, ry, core, rim, sides


def benchmark_shape(
    pdf: Path,
    *,
    page: int = 1,
    dpi: int = 200,
    step: int = 4,
    repeats: int = 2,
    report: Path | None = None,
) -> dict:
    if type(step) is not int or not 1 <= step <= 50:
        raise ValueError("passo fora de 1–50")
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError("repetições fora de 1–10")
    if report is not None and report.exists():
        raise FileExistsError("relatório já existe")
    image = load_pdf_page(pdf, page_number=page, dpi=dpi)
    detection = detect_staffs(image)
    if not detection.staffs:
        raise ValueError("nenhuma pauta detectada")
    staff = detection.staffs[0]
    ink = _ink_without_staff(image, staff, detection.threshold)
    rx, ry, core, rim, sides = _masks(staff.spacing)
    left = max(rx, round(staff.region.left))
    right = min(image.width - rx, round(staff.region.right))
    coordinates = [
        (x, y)
        for degree in range(-4, 13)
        for y in range(
            round(staff.lines[-1].y - degree * staff.spacing / 2 - 0.12 * staff.spacing),
            round(staff.lines[-1].y - degree * staff.spacing / 2 + 0.12 * staff.spacing) + 1,
        )
        for x in range(left, right, step)
        if ry <= y < image.height - ry
    ]
    if not coordinates:
        raise ValueError("pauta sem coordenadas comparáveis")
    prefix_start = perf_counter()
    prefix = _horizontal_ink_prefix(ink, image.width, image.height)
    core_spans = _offset_spans(core)
    rim_spans = _offset_spans(rim)
    side_spans = tuple(_offset_spans(side) for side in sides)
    prefix_build_seconds = perf_counter() - prefix_start
    args = (image.width, image.height)
    original = []
    revised = []
    baseline_seconds = []
    revised_seconds = []
    for _ in range(repeats):
        began = perf_counter()
        original = [
            _shape(ink, *args, x, y, rx, ry, core, rim, sides)
            for x, y in coordinates
        ]
        baseline_seconds.append(perf_counter() - began)
        began = perf_counter()
        revised = [
            _shape_from_prefix(
                prefix, *args, x, y, rx, ry, core, rim, sides,
                core_spans, rim_spans, side_spans,
            )
            for x, y in coordinates
        ]
        revised_seconds.append(perf_counter() - began)
    mismatches = sum(a != b for a, b in zip(original, revised, strict=True))
    result = {
        "format_version": 1,
        "input": pdf.name,
        "page": page,
        "dpi": dpi,
        "staff_index": 0,
        "coordinates_compared": len(coordinates),
        "mismatches": mismatches,
        "matches": len(coordinates) - mismatches,
        "legacy_shape_seconds": baseline_seconds,
        "prefix_shape_seconds": revised_seconds,
        "prefix_build_seconds": round(prefix_build_seconds, 5),
        "median_shape_speedup": (
            round(median(baseline_seconds) / median(revised_seconds), 3)
            if median(revised_seconds) > 0
            else None
        ),
        "prefix_extra_bytes": len(prefix) * 4,
        "classification_accuracy": "not_evaluated",
        "caveat": (
            "Mesmas coordenadas do mesmo PDF e processo, não precisão de "
            "notas nem aceleração end-to-end de todas as etapas."
        ),
    }
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as out:
            json.dump(result, out, indent=2, ensure_ascii=False)
            out.write("\n")
    if mismatches:
        raise ValueError(f"regressão visual em {mismatches} coordenadas")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--step", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = benchmark_shape(
            args.pdf, page=args.page, dpi=args.dpi, step=args.step,
            repeats=args.repeats, report=args.report,
        )
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
