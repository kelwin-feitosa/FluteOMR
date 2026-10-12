"""CLI local: JSON em stdout, erros em stderr."""

import argparse
import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from fluteomr.clefs import detect_treble_clefs
from fluteomr.debug import (
    render_clefs_debug_image,
    render_debug_image,
    render_systems_debug_image,
)
from fluteomr.image_io import load_image
from fluteomr.staff_detection import detect_staffs
from fluteomr.systems import group_staffs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detectar geometria de pautas PNG/JPEG"
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("--debug", type=Path, help="Salvar imagem anotada em PNG")
    parser.add_argument(
        "--systems", action="store_true", help="Agrupar pautas em sistemas no JSON"
    )
    parser.add_argument(
        "--clefs", action="store_true", help="Detectar claves de sol no JSON"
    )
    args = parser.parse_args()
    if args.debug and args.debug.resolve() == args.image.resolve():
        parser.error("A saída de depuração não pode sobrescrever a entrada")
    if args.debug and args.debug.exists():
        parser.error("A saída de depuração já existe; escolha outro caminho")
    try:
        image = load_image(args.image)
        result = detect_staffs(image)
        grouping = group_staffs(result.staffs) if args.systems else None
        clefs = detect_treble_clefs(image, result) if args.clefs else None
        if args.debug:
            annotated = (
                render_clefs_debug_image(image, result, clefs, grouping)
                if clefs is not None
                else render_systems_debug_image(image, result, grouping)
                if grouping is not None
                else render_debug_image(image, result)
            )
            annotated.save(args.debug, format="PNG")
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as e:
        parser.error(str(e))
    payload = result.to_dict()
    if grouping is not None:
        payload["system_grouping"] = grouping.to_dict()
    if clefs is not None:
        payload["clef_detection"] = clefs.to_dict()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
