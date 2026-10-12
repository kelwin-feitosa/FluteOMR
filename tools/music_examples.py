"""Exercícios originais controlados; referências nunca entram na inferência."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from fluteomr.music import Pitch

SPACING = 16
BOTTOM = 138
MEASURE_LEFT = 110
MEASURE_RIGHT = 410

EXERCISES = {
    "dev_lines_spaces": ("development", ((0, "quarter"), (1, "quarter"), (2, "half"))),
    "dev_stems": ("development", ((5, "half"), (8, "half"))),
    "dev_ledger": ("development", ((-2, "quarter"), (0, "quarter"), (10, "half"))),
    "holdout_melody": ("test", ((3, "quarter"), (7, "quarter"), (-1, "half"))),
    "holdout_scaled": (
        "test",
        ((-1, "quarter"), (4, "quarter"), (9, "quarter"), (6, "quarter")),
    ),
}


def degree_pitch(degree: int) -> Pitch:
    offset, position = divmod(2 + degree, 7)
    return Pitch("CDEFGAB"[position], 4 + offset)


def render_exercise(
    notes: tuple[tuple[int, str], ...],
    spacing: int = SPACING,
    positions: tuple[int, ...] | None = None,
) -> Image.Image:
    """Desenha símbolos por primitivas Pillow, independentemente do detector."""
    image = Image.new("RGB", (480, 215), "white")
    draw = ImageDraw.Draw(image)
    bottom = BOTTOM
    for index in range(5):
        y = bottom - index * spacing
        draw.line((25, y, 455, y), fill="black", width=2)
    draw.line(
        (MEASURE_LEFT - 10, bottom - 4 * spacing, MEASURE_LEFT - 10, bottom),
        fill="black",
        width=2,
    )
    draw.line(
        (MEASURE_RIGHT + 10, bottom - 4 * spacing, MEASURE_RIGHT + 10, bottom),
        fill="black",
        width=2,
    )
    draw.text((74, bottom - 4 * spacing + 4), "4", fill="black")
    draw.text((74, bottom - 2 * spacing + 2), "4", fill="black")
    # Marca de clave apenas ilustrativa: a clave de sol é configuração do pipeline.
    draw.arc(
        (38, bottom - 5 * spacing, 67, bottom + spacing), 35, 310, fill="black", width=3
    )
    draw.line((54, bottom + spacing, 54, bottom - 5 * spacing), fill="black", width=2)
    xs = positions or (
        [155, 250, 345]
        if len(notes) == 3
        else [175, 330]
        if len(notes) == 2
        else [145, 215, 285, 355]
    )
    rx, ry = round(0.65 * spacing), round(0.42 * spacing)
    for x, (degree, duration) in zip(xs, notes, strict=True):
        y = round(bottom - degree * spacing / 2)
        ledger_positions = (
            range(-2, degree - 1, -2) if degree < 0 else range(10, degree + 1, 2)
        )
        for ledger_degree in ledger_positions:
            ledger_y = round(bottom - ledger_degree * spacing / 2)
            draw.line(
                (x - rx - 4, ledger_y, x + rx + 4, ledger_y), fill="black", width=2
            )
        box = (x - rx, y - ry, x + rx, y + ry)
        if duration == "quarter":
            draw.ellipse(box, fill="black")
        elif duration == "half":
            draw.ellipse(box, fill="white", outline="black", width=2)
        else:
            raise ValueError("somente quarter e half")
        if degree <= 4:
            draw.line(
                (x + rx - 1, y, x + rx - 1, y - round(3.4 * spacing)),
                fill="black",
                width=2,
            )
        else:
            draw.line(
                (x - rx + 1, y, x - rx + 1, y + round(3.4 * spacing)),
                fill="black",
                width=2,
            )
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description="Gerar exercícios musicais próprios")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/sprint-1a/corpus")
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, (split, notes) in EXERCISES.items():
        scaled = name == "holdout_scaled"
        positions = (
            (135, 205, 285, 365)
            if scaled
            else (155, 250, 345)
            if len(notes) == 3
            else (175, 330)
            if len(notes) == 2
            else (145, 215, 285, 355)
        )
        image = render_exercise(
            notes, spacing=20 if scaled else SPACING, positions=positions
        )
        image.save(args.output_dir / f"{name}.png")
        reference = {
            "split": split,
            "source": "original_programmatic_exercise",
            "image": f"{name}.png",
            "configured": {
                "clef": "treble",
                "time": "4/4",
                "measure_left": MEASURE_LEFT,
                "measure_right": MEASURE_RIGHT,
            },
            "staff_spacing": 20 if scaled else SPACING,
            "notes": [
                {
                    "step": degree_pitch(degree).step,
                    "octave": degree_pitch(degree).octave,
                    "duration": duration,
                    "center_x": x,
                }
                for x, (degree, duration) in zip(positions, notes, strict=True)
            ],
        }
        (args.output_dir / f"{name}.reference.json").write_text(
            json.dumps(reference, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
