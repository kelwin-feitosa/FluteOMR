"""Visualização raster sem dependência de interface gráfica."""

from PIL import Image, ImageDraw

from fluteomr.clefs import ClefDetectionResult
from fluteomr.image_io import normalize_image
from fluteomr.staff_detection import DetectionResult
from fluteomr.systems import SystemGroupingResult


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


def render_systems_debug_image(
    image: Image.Image, result: DetectionResult, grouping: SystemGroupingResult
) -> Image.Image:
    """Sobrepõe retângulos e IDs de sistemas à depuração das pautas."""
    output = render_debug_image(image, result)
    draw = ImageDraw.Draw(output)
    colors = ("#008040", "#8030a0", "#0080a0", "#a05000")
    for system in grouping.systems:
        box = system.region
        color = colors[system.id % len(colors)]
        draw.rectangle(
            (box.left, box.top, box.right, box.bottom), outline=color, width=2
        )
        draw.text(
            (box.left + 2, max(0, round(box.top) - 12)), str(system.id), fill=color
        )
    return output


def render_clefs_debug_image(
    image: Image.Image,
    result: DetectionResult,
    clefs: ClefDetectionResult,
    grouping: SystemGroupingResult | None = None,
) -> Image.Image:
    """Acrescenta caixas verdes às claves aceitas, mantendo as demais camadas."""
    output = (
        render_systems_debug_image(image, result, grouping)
        if grouping is not None
        else render_debug_image(image, result)
    )
    draw = ImageDraw.Draw(output)
    for observation in clefs.observations:
        if observation.clef is None:
            continue
        box = observation.clef.region
        draw.rectangle(
            (box.left, box.top, box.right, box.bottom), outline="lime", width=2
        )
    return output
