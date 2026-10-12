"""CLI local: JSON em stdout, erros em stderr."""

import argparse
import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from fluteomr.debug import render_debug_image
from fluteomr.image_io import load_image
from fluteomr.staff_detection import detect_staffs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detectar geometria de pautas PNG/JPEG"
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("--debug", type=Path, help="Salvar imagem anotada em PNG")
    args = parser.parse_args()
    if args.debug and args.debug.resolve() == args.image.resolve():
        parser.error("A saída de depuração não pode sobrescrever a entrada")
    if args.debug and args.debug.exists():
        parser.error("A saída de depuração já existe; escolha outro caminho")
    try:
        image = load_image(args.image)
        result = detect_staffs(image)
        if args.debug:
            render_debug_image(image, result).save(args.debug, format="PNG")
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as e:
        parser.error(str(e))
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
