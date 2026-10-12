"""Visualização raster sem dependência de interface gráfica."""

from PIL import Image, ImageDraw

from fluteomr.image_io import normalize_image
from fluteomr.staff_detection import DetectionResult


def render_debug_image(image: Image.Image, result: DetectionResult) -> Image.Image:
    """Candidatos em laranja, linhas aceitas em vermelho e regiões em azul."""
    output = normalize_image(image)
    if output.size != (result.width, result.height):
        raise ValueError("Dimensões da imagem e da detecção não coincidem")
    draw = ImageDraw.Draw(output)
    for line in result.candidates:
        draw.line((line.x_start, line.y, line.x_end, line.y), fill="orange")
    for staff in result.staffs:
        box = staff.region
        draw.rectangle((box.left, box.top, box.right, box.bottom), outline="blue")
        for line in staff.lines:
            draw.line((line.x_start, line.y, line.x_end, line.y), fill="red")
    return output
