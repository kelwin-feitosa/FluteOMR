"""Compara contagens com um manifesto sem versionar imagens reais."""

import argparse
import json
from pathlib import Path

from PIL import UnidentifiedImageError

from fluteomr.debug import render_debug_image
from fluteomr.image_io import load_image
from fluteomr.staff_detection import detect_staffs

DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[1] / "tests/data/real_staff_counts.json"
)


def evaluate(
    image_dir: Path, manifest: Path, debug_dir: Path | None = None
) -> tuple[list[tuple[str, int, int | None]], list[str]]:
    expected = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(expected, dict) or not all(
        isinstance(name, str)
        and Path(name).name == name
        and name.lower().endswith((".png", ".jpg", ".jpeg"))
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
        for name, count in expected.items()
    ):
        raise ValueError("Manifesto inválido: use nome de arquivo e contagem inteira")
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=False)
    rows = []
    failures = []
    for name, count in expected.items():
        path = image_dir / name
        if not path.is_file():
            rows.append((name, count, None))
            failures.append(f"{name}: arquivo ausente")
            continue
        try:
            image = load_image(path)
            result = detect_staffs(image)
        except (OSError, ValueError, UnidentifiedImageError) as exc:
            rows.append((name, count, None))
            failures.append(f"{name}: {exc}")
            continue
        rows.append((name, count, result.staff_count))
        if debug_dir is not None:
            render_debug_image(image, result).save(debug_dir / f"{path.stem}-debug.png")
    return rows, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-dir", type=Path, default=Path("outputs/teste-real"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--debug-dir", type=Path)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    try:
        rows, failures = evaluate(args.images_dir, args.manifest, args.debug_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    for name, expected, detected in rows:
        difference = "missing" if detected is None else str(detected - expected)
        print(
            f"{name}: expected={expected} detected={detected} difference={difference}"
        )
    known = [row for row in rows if row[2] is not None]
    print(
        "TOTAL: "
        f"expected={sum(row[1] for row in rows)} "
        f"detected={sum(row[2] for row in known)} "
        f"evaluated={len(known)}/{len(rows)} "
        "difference="
        + ("unknown" if failures else str(sum(row[2] - row[1] for row in known)))
    )
    for failure in failures:
        print(f"ERROR: {failure}")
    if failures:
        return 2
    if args.validate and any(expected != detected for _, expected, detected in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
