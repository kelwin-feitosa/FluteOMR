"""Leitura local e normalização de imagens rasterizadas."""

from pathlib import Path

from PIL import Image, ImageOps

MAX_PIXELS = 20_000_000


def normalize_image(image: Image.Image) -> Image.Image:
    """Orientação EXIF aplicada; transparência composta sobre fundo branco."""
    if image.width == 0 or image.height == 0:
        raise ValueError("A imagem deve ter largura e altura positivas")
    if image.width * image.height > MAX_PIXELS:
        raise ValueError(f"Imagem excede o limite de {MAX_PIXELS} pixels")
    oriented = ImageOps.exif_transpose(image)
    if "A" not in oriented.getbands() and "transparency" not in oriented.info:
        return oriented.convert("RGB")
    rgba = oriented.convert("RGBA")
    background = Image.new("RGBA", rgba.size, "white")
    return Image.alpha_composite(background, rgba).convert("RGB")


def load_image(path: str | Path) -> Image.Image:
    """Carrega apenas PNG/JPEG; o resultado não depende do arquivo aberto."""
    with Image.open(path) as image:
        if image.format not in {"PNG", "JPEG"}:
            raise ValueError("Formato não suportado: use PNG ou JPEG")
        return normalize_image(image)
