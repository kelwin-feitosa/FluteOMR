"""Pacotes de revisão musical; não executa detectores nem valida sugestões sozinho."""

import hashlib
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from fluteomr.image_io import normalize_image
from fluteomr.music_evaluation import parse_reference


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _local(directory: Path, name: str) -> Path:
    if not isinstance(name, str) or Path(name).name != name or name in ("", ".", ".."):
        raise ValueError("use nome de arquivo local no pacote")
    return directory / name


def _write(path: Path, data: dict) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _check_xml(path: Path, measures: list[int]) -> None:
    parts = parse_reference(path.read_bytes())
    if len(parts) != 1 or [m.number for m in parts[0]] != measures:
        raise ValueError("referência não corresponde aos compassos/parte do recorte")
    if not any(m.events for m in parts[0]):
        raise ValueError("referência sem eventos")


def prepare_review(
    source: Path,
    directory: Path,
    *,
    example_id: str,
    crop: tuple[int, int, int, int],
    scale: int,
    reference: Path | None,
    measures: tuple[int, ...],
    staff_id: str | None,
    system_id: str | None,
    configured: dict,
    source_page: int = 1,
    work_id: str | None = None,
) -> Path:
    """Cria pacote novo; crop usa bordas PIL exclusivas em right/bottom."""
    if (
        not example_id.strip()
        or type(scale) is not int
        or scale < 1
        or type(source_page) is not int
        or source_page < 1
        or len(crop) != 4
        or any(type(v) is not int for v in crop)
    ):
        raise ValueError("ID, escala ou página inválidos")
    if not measures or any(type(n) is not int or n < 1 for n in measures):
        raise ValueError("informe números positivos de compassos")
    if list(measures) != sorted(set(measures)):
        raise ValueError("compassos devem estar ordenados e sem repetição")
    if reference is not None:
        _check_xml(reference, list(measures))
    with Image.open(source) as original:
        original = normalize_image(original)
        left, top, right, bottom = crop
        if not (
            0 <= left < right <= original.width and 0 <= top < bottom <= original.height
        ):
            raise ValueError("recorte fora da imagem")
        region = original.convert("RGB").crop(crop)
        size = list(original.size)
    directory.mkdir(parents=True, exist_ok=False)
    image_path = directory / "image.png"
    region.resize(
        (region.width * scale, region.height * scale), Image.Resampling.BICUBIC
    ).save(image_path)
    if reference is not None:
        shutil.copyfile(reference, directory / "reference.musicxml")
    review = {
        "format_version": 1,
        "status": "draft",
        "reviewer": None,
        "source": {
            "path": os.path.relpath(source.resolve(), directory.resolve()),
            "sha256": _sha(source),
            "size": size,
            "page": source_page,
            "crop": list(crop),
        },
        "image": {
            "path": image_path.name,
            "sha256": _sha(image_path),
            "size": [region.width * scale, region.height * scale],
        },
        "mapping": {
            "coordinate_frame": "exif_oriented_source",
            "resampling": "bicubic",
            "scale_x": scale,
            "scale_y": scale,
            "pixel_center_formula": (
                "source = crop_origin + (derived + 0.5) / scale - 0.5"
            ),
        },
        "scope": {
            "staff_id": staff_id,
            "system_id": system_id,
            "measures": list(measures),
        },
        "reference": {"path": "reference.musicxml", "sha256": None},
    }
    manifest = {
        "format_version": 1,
        "examples": [
            {
                "id": example_id,
                "work_id": work_id or source.stem,
                "image": image_path.name,
                "reference": "reference.musicxml" if reference else None,
                "origin": "external_image_pending_human_review",
                "source_category": "real_unannotated",
                "split": "development",
                "reference_status": "draft" if reference else "missing",
                "configured": configured,
                "review": "review.json",
            }
        ],
    }
    _write(directory / "review.json", review)
    path = directory / "manifest.json"
    _write(path, manifest)
    return path


def verify_review(manifest_path: Path, example: dict) -> dict:
    """Verifica integridade, inclusive do XML selado; não confirma correção musical."""
    directory = manifest_path.parent
    review = json.loads(
        _local(directory, example["review"]).read_text(encoding="utf-8")
    )
    if review.get("format_version") != 1 or review.get("status") not in (
        "draft",
        "validated",
    ):
        raise ValueError("formato/estado de revisão inválido")
    validated = example["reference_status"] == "validated"
    if validated != (review["status"] == "validated"):
        raise ValueError("estado da revisão e do manifesto divergem")
    source = review["source"]
    if Path(source["path"]).is_absolute():
        raise ValueError("origem deve ter caminho relativo")
    if _sha(directory / source["path"]) != source["sha256"]:
        raise ValueError("hash da origem divergente")
    image = _local(directory, example["image"])
    if (
        example["image"] != review["image"]["path"]
        or _sha(image) != review["image"]["sha256"]
    ):
        raise ValueError("hash da imagem divergente")
    with Image.open(image) as rendered:
        if list(rendered.size) != review["image"]["size"]:
            raise ValueError("dimensões divergentes")
        with Image.open(directory / source["path"]) as original:
            original = normalize_image(original)
            left, top, right, bottom = source["crop"]
            scale = review["mapping"]["scale_x"]
            if (
                list(original.size) != source["size"]
                or type(scale) is not int
                or scale < 1
                or review["mapping"]["scale_y"] != scale
                or review["mapping"]["resampling"] != "bicubic"
                or any(type(v) is not int for v in source["crop"])
                or not (
                    0 <= left < right <= original.width
                    and 0 <= top < bottom <= original.height
                )
                or rendered.size != ((right - left) * scale, (bottom - top) * scale)
            ):
                raise ValueError("geometria de origem inválida")
            expected = (
                original.convert("RGB")
                .crop(source["crop"])
                .resize(rendered.size, Image.Resampling.BICUBIC)
            )
            if expected.tobytes() != rendered.convert("RGB").tobytes():
                raise ValueError("recorte não corresponde à origem")
    reference = _local(directory, review["reference"]["path"])
    if validated:
        if not review.get("reviewer") or example["reference"] != reference.name:
            raise ValueError("confirmação humana incompleta")
        if _sha(reference) != review["reference"]["sha256"]:
            raise ValueError("hash da referência divergente; requer nova revisão")
    if reference.exists():
        _check_xml(reference, review["scope"]["measures"])
    return review


def confirm_review(
    manifest_path: Path, *, reviewer: str, confirm_reviewed: bool
) -> None:
    """Sela somente após declaração explícita do humano; nunca chama OMR."""
    if not confirm_reviewed or not reviewer.strip():
        raise ValueError("confirme a revisão humana e informe o revisor")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if len(manifest["examples"]) != 1:
        raise ValueError("confirme somente um pacote de cada vez")
    example = manifest["examples"][0]
    if example["split"] == "test":
        raise ValueError("revisão de conjunto reservado exige procedimento separado")
    review = verify_review(manifest_path, example)
    if review["status"] == "validated":
        raise ValueError(
            "referência já validada; preserve e crie novo pacote para revisão"
        )
    reference = _local(manifest_path.parent, review["reference"]["path"])
    if not reference.exists():
        raise ValueError("referência musical ausente")
    _check_xml(reference, review["scope"]["measures"])
    review.update(
        status="validated",
        reviewer=reviewer.strip(),
        reviewed_at=datetime.now(UTC).isoformat(),
    )
    review["reference"]["sha256"] = _sha(reference)
    example.update(reference=reference.name, reference_status="validated")
    _write(_local(manifest_path.parent, example["review"]), review)
    _write(manifest_path, manifest)
