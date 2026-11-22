"""Formato versionado de referências revisadas, separado das sugestões."""

import hashlib
import json
import math
import re
from pathlib import Path

from fluteomr.image_io import load_image

SCHEMA_VERSION = 1
STATES = {"complete", "partial", "unknown"}


class AnnotationError(ValueError):
    """Arquivo de anotação inválido ou incompatível com a imagem."""


def image_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object(value, label: str, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise AnnotationError(f"{label}: campos esperados {sorted(keys)}")
    return value


def _integer(value, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise AnnotationError(f"{label}: inteiro >= {minimum} esperado")
    return value


def _number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnnotationError(f"{label}: número esperado")
    if not math.isfinite(value):
        raise AnnotationError(f"{label}: número finito esperado")
    return float(value)


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnnotationError(f"{label}: texto não vazio esperado")
    return value


def _box(value, label: str, width: int, height: int) -> dict | None:
    if value is None:
        return None
    box = _object(value, label, {"left", "top", "right", "bottom"})
    left = _number(box["left"], f"{label}.left")
    top = _number(box["top"], f"{label}.top")
    right = _number(box["right"], f"{label}.right")
    bottom = _number(box["bottom"], f"{label}.bottom")
    if not (0 <= left <= right < width and 0 <= top <= bottom < height):
        raise AnnotationError(f"{label}: caixa fora da imagem ou invertida")
    return box


def _ordered(records: list[dict], label: str) -> None:
    if [item["order"] for item in records] != list(range(len(records))):
        raise AnnotationError(f"{label}: ordem deve ser 0..n-1 na lista")


def validate_reference(data: object, *, require_validated: bool = False) -> dict:
    """Valida estrutura e invariantes; não transforma sugestões em referência."""
    root = _object(
        data,
        "reference",
        {
            "schema_version",
            "kind",
            "split",
            "review",
            "image",
            "coverage",
            "staffs",
            "systems",
            "clefs",
        },
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or type(root["schema_version"]) is not int
    ):
        raise AnnotationError("schema_version não suportado")
    if root["kind"] != "reference":
        raise AnnotationError("kind deve ser reference")
    if type(root["split"]) is not str or root["split"] not in {
        "development",
        "test",
        "unspecified",
    }:
        raise AnnotationError("split inválido")
    review = _object(root["review"], "review", {"status", "confirmed_by"})
    if type(review["status"]) is not str or review["status"] not in {
        "draft",
        "validated",
    }:
        raise AnnotationError("review.status inválido")
    if review["status"] == "validated":
        _text(review["confirmed_by"], "review.confirmed_by")
        if root["split"] == "unspecified":
            raise AnnotationError("referência validada exige split development ou test")
    elif review["confirmed_by"] is not None:
        raise AnnotationError("rascunho não pode ter confirmed_by")
    if require_validated and review["status"] != "validated":
        raise AnnotationError("referência ainda não validada por humano")

    image = _object(
        root["image"], "image", {"id", "filename", "sha256", "width", "height"}
    )
    _text(image["id"], "image.id")
    filename = _text(image["filename"], "image.filename")
    if Path(filename).name != filename or not filename.lower().endswith(
        (".png", ".jpg", ".jpeg")
    ):
        raise AnnotationError("image.filename deve ser nome simples PNG/JPEG")
    if not isinstance(image["sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", image["sha256"]
    ):
        raise AnnotationError("image.sha256 inválido")
    width = _integer(image["width"], "image.width", 1)
    height = _integer(image["height"], "image.height", 1)
    coverage = _object(root["coverage"], "coverage", {"staffs", "systems", "clefs"})
    if any(
        type(value) is not str or value not in STATES for value in coverage.values()
    ):
        raise AnnotationError("coverage: use complete, partial ou unknown")

    staffs = root["staffs"]
    if not isinstance(staffs, list):
        raise AnnotationError("staffs: lista esperada")
    staff_ids: set[str] = set()
    for staff in staffs:
        _object(staff, "staff", {"id", "order", "review_state", "region", "lines"})
        staff_id = _text(staff["id"], "staff.id")
        if staff_id in staff_ids:
            raise AnnotationError("staff.id duplicado")
        staff_ids.add(staff_id)
        _integer(staff["order"], "staff.order")
        if type(staff["review_state"]) is not str or staff["review_state"] not in {
            "confirmed",
            "partial",
            "unknown",
        }:
            raise AnnotationError("staff.review_state inválido")
        region = _box(staff["region"], "staff.region", width, height)
        if staff["review_state"] == "confirmed" and region is None:
            raise AnnotationError("pauta confirmada exige região")
        lines = staff["lines"]
        if lines is not None:
            if region is None or not isinstance(lines, list) or len(lines) != 5:
                raise AnnotationError("staff.lines exige região e cinco linhas")
            previous_y = -1.0
            for line in lines:
                _object(line, "line", {"x_start", "x_end", "y"})
                x_start = _number(line["x_start"], "line.x_start")
                x_end = _number(line["x_end"], "line.x_end")
                y = _number(line["y"], "line.y")
                if not (
                    region["left"] <= x_start <= x_end <= region["right"]
                    and region["top"] <= y <= region["bottom"]
                    and y > previous_y
                ):
                    raise AnnotationError("staff.lines fora da região ou sem ordem")
                previous_y = y
    _ordered(staffs, "staffs")
    if (
        review["status"] == "validated"
        and not any(staff["review_state"] == "confirmed" for staff in staffs)
        and not (coverage["staffs"] == "complete" and not staffs)
    ):
        raise AnnotationError("referência validada sem pauta revisada")
    if coverage["staffs"] == "complete" and any(
        staff["review_state"] != "confirmed" for staff in staffs
    ):
        raise AnnotationError("cobertura completa exige pautas confirmadas")

    systems = root["systems"]
    if not isinstance(systems, list):
        raise AnnotationError("systems: lista esperada")
    system_ids: set[str] = set()
    assigned: set[str] = set()
    for system in systems:
        _object(
            system,
            "system",
            {"id", "order", "staff_ids", "review_state", "partial_visible"},
        )
        system_id = _text(system["id"], "system.id")
        if system_id in system_ids:
            raise AnnotationError("system.id duplicado")
        system_ids.add(system_id)
        _integer(system["order"], "system.order")
        if type(system["review_state"]) is not str or system["review_state"] not in {
            "confirmed",
            "uncertain",
        }:
            raise AnnotationError("system.review_state inválido")
        if type(system["partial_visible"]) is not bool:
            raise AnnotationError("system.partial_visible deve ser booleano")
        members = system["staff_ids"]
        if (
            not isinstance(members, list)
            or not members
            or any(not isinstance(member, str) for member in members)
            or len(set(members)) != len(members)
        ):
            raise AnnotationError("system.staff_ids inválidos")
        if any(member not in staff_ids for member in members):
            raise AnnotationError("system.staff_ids referencia pauta inexistente")
        if system["review_state"] == "confirmed":
            if assigned.intersection(members):
                raise AnnotationError("pauta em mais de um sistema confirmado")
            assigned.update(members)
    _ordered(systems, "systems")
    if coverage["systems"] == "complete":
        if (
            coverage["staffs"] != "complete"
            or assigned != staff_ids
            or any(system["review_state"] != "confirmed" for system in systems)
        ):
            raise AnnotationError("sistemas completos exigem partição confirmada")

    clefs = root["clefs"]
    if not isinstance(clefs, list):
        raise AnnotationError("clefs: lista esperada")
    clef_staff_ids: set[str] = set()
    for clef in clefs:
        _object(clef, "clef", {"staff_id", "state", "kind", "region"})
        staff_id = _text(clef["staff_id"], "clef.staff_id")
        if staff_id not in staff_ids or staff_id in clef_staff_ids:
            raise AnnotationError("clef.staff_id ausente ou duplicado")
        clef_staff_ids.add(staff_id)
        if type(clef["state"]) is not str or clef["state"] not in {
            "present",
            "absent",
            "unknown",
        }:
            raise AnnotationError("clef.state inválido")
        _box(clef["region"], "clef.region", width, height)
        if clef["state"] == "present":
            if type(clef["kind"]) is not str or clef["kind"] not in {
                "treble",
                "bass",
                "alto",
                "other",
            }:
                raise AnnotationError("clave presente exige kind válido")
        elif clef["kind"] is not None or clef["region"] is not None:
            raise AnnotationError("clave ausente/desconhecida não tem kind/região")
    if review["status"] == "validated" and clef_staff_ids != staff_ids:
        raise AnnotationError("referência validada exige estado de clave por pauta")
    if coverage["clefs"] == "complete" and (
        coverage["staffs"] != "complete"
        or clef_staff_ids != staff_ids
        or any(clef["state"] == "unknown" for clef in clefs)
    ):
        raise AnnotationError("claves completas exigem estado conhecido por pauta")
    return root


def verify_image(reference: dict, image_dir: Path) -> Path:
    """Compara bytes SHA-256 e dimensões normalizadas, sem caminho absoluto."""
    filename = reference["image"]["filename"]
    # Public callers must not rely on validate_reference() having run first.
    # Reject traversal and symlinks escaping the configured image directory.
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or "\\" in filename
        or filename in (".", "..")
    ):
        raise AnnotationError("image.filename deve ser nome simples")
    path = image_dir / filename
    trusted_root = image_dir.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(trusted_root):
        raise AnnotationError("imagem fora do diretório permitido")
    if not resolved_path.is_file():
        raise FileNotFoundError(f"imagem ausente: {path.name}")
    actual_hash = image_sha256(resolved_path)
    if actual_hash != reference["image"]["sha256"]:
        raise AnnotationError(f"hash SHA-256 diferente: {path.name}")
    image = load_image(resolved_path)
    if image.size != (reference["image"]["width"], reference["image"]["height"]):
        raise AnnotationError(f"dimensões diferentes: {path.name}")
    return path


def load_reference(path: Path, *, require_validated: bool = False) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AnnotationError(f"JSON inválido: {path.name}: {exc}") from exc
    return validate_reference(data, require_validated=require_validated)
