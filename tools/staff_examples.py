"""Exemplos próprios com ground truth e avaliação quantitativa reproduzível.

Executar da raiz: python -m tools.staff_examples --output outputs/staff-demo
"""

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from PIL import Image, ImageDraw

from fluteomr.debug import render_debug_image
from fluteomr.staff_detection import detect_staffs


@dataclass
class Example:
    name: str
    image: Image.Image
    centers: tuple[tuple[float, ...], ...]
    expected_status: str
    supported: bool = True


def make_staff_image(
    *,
    size: tuple[int, int] = (640, 240),
    tops: tuple[int, ...] = (40,),
    spacing: int = 12,
    thickness: int = 1,
    symbols: bool = False,
    noise: float = 0,
    gaps: bool = False,
) -> tuple[Image.Image, tuple[tuple[float, ...], ...]]:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    margin = round(size[0] * 0.06)
    centers = []
    for top in tops:
        positions = tuple(top + i * spacing + (thickness - 1) / 2 for i in range(5))
        centers.append(positions)
        for i in range(5):
            y = top + i * spacing
            draw.rectangle(
                (margin, y, size[0] - margin - 1, y + thickness - 1), fill="black"
            )
            if gaps:
                for x in range(margin + spacing * 4, size[0] - margin, spacing * 7):
                    draw.rectangle(
                        (x, y, x + thickness * 2, y + thickness - 1), "white"
                    )
        if symbols:
            for i in range(3):
                x, y = margin + spacing * (6 + i * 9), top + spacing * (i + 1)
                draw.ellipse(
                    (x, y - spacing / 3, x + spacing, y + spacing / 3), "black"
                )
                draw.line((x + spacing, y, x + spacing, y - spacing * 2), "black", 2)
            draw.line((size[0] // 2, top, size[0] // 2, top + 4 * spacing), "black", 2)
    rng = random.Random(20261012)
    for _ in range(round(size[0] * size[1] * noise)):
        image.putpixel((rng.randrange(size[0]), rng.randrange(size[1])), (0, 0, 0))
    return image, tuple(centers)


def examples() -> list[Example]:
    cases = []
    settings = {
        "clean": {},
        "shifted": {"tops": (91,)},
        "thick": {"spacing": 18, "thickness": 3},
        "even_thickness": {"spacing": 14, "thickness": 2},
        "two_staffs": {"tops": (25, 140)},
        "symbols": {"symbols": True},
        "noise": {"noise": 0.005},
        "interrupted": {"gaps": True, "symbols": True},
        "small": {"size": (160, 100), "tops": (3,), "spacing": 6},
        "large": {"size": (1280, 480), "spacing": 24, "thickness": 4},
    }
    for name, kwargs in settings.items():
        image, centers = make_staff_image(**kwargs)
        cases.append(Example(name, image, centers, "detected"))
    cases.append(
        Example("blank", Image.new("RGB", (320, 140), "white"), (), "no_staff")
    )
    for name, positions, status in (
        ("insufficient", [30, 42, 54, 66], "no_staff"),
        ("inconsistent", [20, 32, 44, 70, 82], "no_staff"),
        ("six_lines", [20, 32, 44, 56, 68, 80], "ambiguous"),
    ):
        image = Image.new("RGB", (320, 140), "white")
        draw = ImageDraw.Draw(image)
        for y in positions:
            draw.line((20, y, 299, y), "black")
        cases.append(Example(name, image, (), status))
    # Falhas conhecidas: geometria sozinha não distingue papel pautado de música.
    ruled, _ = make_staff_image()
    cases.append(Example("nonmusical_ruling", ruled, (), "no_staff", supported=False))
    skewed, centers = make_staff_image()
    skewed = skewed.rotate(2, resample=Image.Resampling.BICUBIC, fillcolor="white")
    cases.append(
        Example("skew_2_degrees", skewed, centers, "detected", supported=False)
    )
    return cases


def evaluate(case: Example) -> dict:
    started = perf_counter()
    result = detect_staffs(case.image)
    elapsed_ms = (perf_counter() - started) * 1000
    errors = []
    if len(result.staffs) == len(case.centers):
        for staff, expected in zip(result.staffs, case.centers, strict=True):
            errors.extend(
                abs(line.y - y) for line, y in zip(staff.lines, expected, strict=True)
            )
    passed = (
        result.status == case.expected_status
        and result.staff_count == len(case.centers)
        and all(error <= 2 for error in errors)
    )
    return {
        "name": case.name,
        "supported": case.supported,
        "passed": passed,
        "expected_status": case.expected_status,
        "status": result.status,
        "expected_count": len(case.centers),
        "count": result.staff_count,
        "max_center_error_px": max(errors, default=None),
        "elapsed_ms": round(elapsed_ms, 3),
        "ground_truth_centers": case.centers,
        "detection": result.to_dict(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Diretório já existe; escolha outro para preservar resultados")
    args.output.mkdir(parents=True)
    records = []
    for case in examples():
        case.image.save(args.output / f"{case.name}.png")
        record = evaluate(case)
        render_debug_image(case.image, detect_staffs(case.image)).save(
            args.output / f"{case.name}-debug.png"
        )
        records.append(record)
    report = {
        "supported_passed": sum(r["passed"] for r in records if r["supported"]),
        "supported_total": sum(r["supported"] for r in records),
        "cases": records,
    }
    (args.output / "evaluation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
