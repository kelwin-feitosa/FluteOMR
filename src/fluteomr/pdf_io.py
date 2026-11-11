"""Renderização de páginas PDF para o motor OMR próprio.

PDFium é usado somente para rasterizar; o reconhecimento musical continua no
FluteOMR. A resolução e os limites são verificados antes de alocar o bitmap.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from math import ceil, isfinite
from pathlib import Path

from PIL import Image

from fluteomr.image_io import MAX_PIXELS, normalize_image

MAX_PDF_BYTES = 128 * 1024 * 1024
MAX_PDF_PAGES = 1000
MIN_DPI = 72
MAX_DPI = 400


class PdfInputError(ValueError):
    """PDF ilegível, página inválida ou custo de rasterização excessivo."""


@contextmanager
def _open_pdf(path: str | Path) -> Iterator:
    source = Path(path)
    size = source.stat().st_size
    if not 0 < size <= MAX_PDF_BYTES:
        raise PdfInputError("PDF vazio ou acima do limite de 128 MiB")
    with source.open("rb") as stream:
        if b"%PDF-" not in stream.read(1024):
            raise PdfInputError("arquivo não contém cabeçalho PDF válido")
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise PdfInputError(
            "PDF requer dependência opcional: pip install 'fluteomr[pdf]'"
        ) from exc
    try:
        document = pdfium.PdfDocument(str(source))
    except pdfium.PdfiumError as exc:
        raise PdfInputError(f"não foi possível abrir o PDF: {exc}") from exc
    try:
        if not 0 < len(document) <= MAX_PDF_PAGES:
            raise PdfInputError("PDF vazio ou acima do limite de 1000 páginas")
        yield document
    finally:
        document.close()


def pdf_page_count(path: str | Path) -> int:
    """Conta páginas, sem rasterizar nem executar reconhecimento musical."""
    with _open_pdf(path) as document:
        return len(document)


def load_pdf_page(
    path: str | Path, *, page_number: int = 1, dpi: int | float = 200
) -> Image.Image:
    """Retorna página PDF em RGB normalizado (contagem iniciada em um).

    A alocação é limitada ao máximo de pixels do pipeline PNG/JPEG. Os recursos
    nativos do PDFium são liberados mesmo quando a renderização falha.
    """
    if type(page_number) is not int or page_number < 1:
        raise PdfInputError("page_number deve ser inteiro positivo")
    if (
        isinstance(dpi, bool)
        or not isinstance(dpi, (int, float))
        or not isfinite(dpi)
        or not MIN_DPI <= dpi <= MAX_DPI
    ):
        raise PdfInputError(f"dpi deve estar entre {MIN_DPI} e {MAX_DPI}")

    with _open_pdf(path) as document:
        if page_number > len(document):
            raise PdfInputError(
                f"página {page_number} fora do PDF ({len(document)} páginas)"
            )
        page = document[page_number - 1]
        try:
            width, height = page.get_size()
            scale = dpi / 72
            if not isfinite(width) or not isfinite(height) or width <= 0 or height <= 0:
                raise PdfInputError("dimensões da página PDF inválidas")
            pixels = ceil(width * scale) * ceil(height * scale)
            if pixels > MAX_PIXELS:
                raise PdfInputError(
                    f"página excederia {MAX_PIXELS} pixels em {dpi:g} DPI; "
                    "escolha uma resolução menor"
                )
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil().copy()
            finally:
                bitmap.close()
        finally:
            page.close()
    return normalize_image(image)
