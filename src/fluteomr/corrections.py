"""Correções operacionais de claves, separadas de sugestões e referências."""

import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from threading import Lock

from fluteomr.annotations import image_sha256
from fluteomr.image_io import load_image

SCHEMA_VERSION = 1
KINDS = {"treble", "bass", "alto", "other"}


class CorrectionError(ValueError):
    """Entrada inválida ou fontes incompatíveis."""


class RevisionConflict(CorrectionError):
    """O arquivo mudou depois da última leitura."""


def _box(value: object, width: int, height: int) -> dict:
    if not isinstance(value, dict) or set(value) != {"left", "top", "right", "bottom"}:
        raise CorrectionError("região exige left, top, right e bottom")
    if any(type(value[key]) is not int for key in value):
        raise CorrectionError("coordenadas da correção devem ser inteiras")
    left, top, right, bottom = (
        value[key] for key in ("left", "top", "right", "bottom")
    )
    if not (0 <= left < right < width and 0 <= top < bottom < height):
        raise CorrectionError("região fora da imagem ou sem área positiva")
    return value.copy()


def _source_image(info: object, images_dir: Path) -> Path:
    if not isinstance(info, dict) or set(info) != {
        "id",
        "filename",
        "sha256",
        "width",
        "height",
    }:
        raise CorrectionError("identidade da imagem inválida")
    name = info["filename"]
    if (
        not isinstance(name, str)
        or Path(name).name != name
        or name in (".", "..")
        or not name.lower().endswith((".png", ".jpg", ".jpeg"))
    ):
        raise CorrectionError("nome da imagem inválido")
    if type(info["width"]) is not int or type(info["height"]) is not int:
        raise CorrectionError("dimensões da imagem inválidas")
    if info["width"] < 1 or info["height"] < 1:
        raise CorrectionError("dimensões da imagem inválidas")
    if not isinstance(info["sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", info["sha256"]
    ):
        raise CorrectionError("hash da imagem inválido")
    path = images_dir / name
    if not path.is_file() or path.is_symlink():
        raise CorrectionError("imagem não encontrada no diretório configurado")
    if image_sha256(path) != info["sha256"]:
        raise CorrectionError("hash da imagem diferente das sugestões")
    if load_image(path).size != (info["width"], info["height"]):
        raise CorrectionError("dimensões da imagem diferentes das sugestões")
    return path


def _validate_suggestions(data: object, images_dir: Path) -> Path:
    if (
        not isinstance(data, dict)
        or data.get("kind") != "suggestions_not_ground_truth"
        or type(data.get("schema_version")) is not int
        or data["schema_version"] != SCHEMA_VERSION
    ):
        raise CorrectionError("arquivo de sugestões inválido")
    image = data.get("image")
    path = _source_image(image, images_dir)
    detections = data.get("detections")
    if not isinstance(detections, dict):
        raise CorrectionError("detecções ausentes")
    staffs, clefs = detections.get("staffs"), detections.get("clefs")
    if (
        not isinstance(staffs, list)
        or not isinstance(clefs, list)
        or len(staffs) != len(clefs)
    ):
        raise CorrectionError("pautas e claves incompatíveis")
    for staff, clef in zip(staffs, clefs, strict=True):
        if not isinstance(staff, dict) or not isinstance(staff.get("region"), dict):
            raise CorrectionError("região de pauta ausente")
        box = staff["region"]
        if set(box) != {"left", "top", "right", "bottom"} or any(
            isinstance(box[key], bool)
            or not isinstance(box[key], (int, float))
            or not math.isfinite(box[key])
            for key in box
        ):
            raise CorrectionError("região de pauta inválida")
        if not (
            0 <= box["left"] < box["right"] < image["width"]
            and 0 <= box["top"] < box["bottom"] < image["height"]
        ):
            raise CorrectionError("região de pauta fora da imagem")
        if not isinstance(clef, dict) or clef.get("status") not in {
            "detected",
            "inconclusive",
            "no_treble",
        }:
            raise CorrectionError("estado de clave inválido")
        region = clef.get("region")
        if (clef["status"] == "detected") != (region is not None):
            raise CorrectionError("estado e região da clave discordam")
        if region is not None:
            _box(region, image["width"], image["height"])
    systems = detections.get("systems")
    if not isinstance(systems, dict) or not isinstance(systems.get("groups"), list):
        raise CorrectionError("agrupamento de sistemas inválido")
    return path


def validate_decisions(
    decisions: object, staff_count: int, width: int, height: int
) -> dict:
    """Exige ação explícita: nenhuma chave implica predição ainda automática."""
    if not isinstance(decisions, dict):
        raise CorrectionError("decisions deve ser objeto")
    result = {}
    for staff_id, decision in decisions.items():
        if staff_id not in {f"s{index}" for index in range(staff_count)}:
            raise CorrectionError("ID de pauta desconhecido")
        if not isinstance(decision, dict) or set(decision) != {
            "state",
            "kind",
            "region",
        }:
            raise CorrectionError("decisão exige state, kind e region")
        state, kind, region = (decision[key] for key in ("state", "kind", "region"))
        if state == "present":
            if kind not in KINDS:
                raise CorrectionError("tipo de clave inválido")
            region = _box(region, width, height)
        elif state == "absent":
            if kind is not None or region is not None:
                raise CorrectionError("ausência não possui tipo ou região")
        else:
            raise CorrectionError("state deve ser present ou absent")
        result[staff_id] = {"state": state, "kind": kind, "region": region}
    return result


def visual_state(suggestions: dict, decisions: dict) -> dict:
    """Combina camadas para a UI sem converter predições em revisão humana."""
    detections = suggestions["detections"]
    clefs = []
    for index, (staff, prediction) in enumerate(
        zip(detections["staffs"], detections["clefs"], strict=True)
    ):
        staff_id = f"s{index}"
        correction = decisions.get(staff_id)
        if correction is not None:
            effective = {**correction, "source": "user_correction"}
        elif prediction["status"] == "detected":
            effective = {
                "state": "present",
                "kind": "treble",
                "region": prediction["region"],
                "source": "automatic_prediction",
            }
        else:
            effective = {
                "state": "unknown",
                "kind": None,
                "region": None,
                "source": "unresolved_prediction",
            }
        clefs.append(
            {
                "staff_id": staff_id,
                "staff_region": staff["region"],
                "prediction": prediction,
                "correction": correction,
                "effective": effective,
                "pending": effective["state"] == "unknown",
            }
        )
    return {
        "clefs": clefs,
        "counts": {
            "staffs": len(clefs),
            "automatic_detected": sum(
                c["prediction"]["status"] == "detected" for c in clefs
            ),
            "pending": sum(c["pending"] for c in clefs),
            "corrected": sum(c["correction"] is not None for c in clefs),
        },
        "systems": detections["systems"],
    }


class PageCatalog:
    """Lista apenas sugestões encontradas em um diretório configurado pelo operador."""

    def __init__(self, images_dir: Path, suggestions_dir: Path, corrections_dir: Path):
        self.images_dir = Path(images_dir)
        self.suggestions_dir = Path(suggestions_dir)
        self.corrections_dir = Path(corrections_dir)
        if not self.images_dir.is_dir() or not self.suggestions_dir.is_dir():
            raise CorrectionError("diretórios de imagens/sugestões ausentes")
        correction_root = self.corrections_dir.resolve()
        if self.corrections_dir.is_symlink() or any(
            correction_root.is_relative_to(source.resolve())
            for source in (self.images_dir, self.suggestions_dir)
        ):
            raise CorrectionError("diretório de correções deve ser separado")
        self._pages = {}
        for path in sorted(self.suggestions_dir.glob("**/*.suggestions.json")):
            relative = path.relative_to(self.suggestions_dir)
            if path.is_symlink() or any(
                (self.suggestions_dir / parent).is_symlink()
                for parent in relative.parents
                if parent != Path(".")
            ):
                continue
            raw = path.read_bytes()
            try:
                data = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CorrectionError(
                    f"JSON de sugestões inválido: {path.name}"
                ) from exc
            info = data.get("image") if isinstance(data, dict) else None
            if not isinstance(info, dict) or not isinstance(info.get("filename"), str):
                raise CorrectionError(f"imagem ausente em {path.name}")
            page_id = hashlib.sha256(
                (info["filename"] + "\0" + str(info.get("sha256"))).encode()
            ).hexdigest()[:20]
            if page_id in self._pages:
                raise CorrectionError("IDs de página duplicados")
            self._pages[page_id] = (path, data, hashlib.sha256(raw).hexdigest())
        if not self._pages:
            raise CorrectionError("nenhuma sugestão encontrada")
        self._lock = Lock()

    def pages(self) -> list[dict]:
        pages = []
        for page_id in self._pages:
            source, source_hash, _ = self._source(page_id)
            corrections = self._load_corrections(page_id, source, source_hash)
            counts = visual_state(source, corrections["decisions"])["counts"]
            pages.append(
                {
                    "id": page_id,
                    "name": source["image"]["filename"],
                    "staff_count": counts["staffs"],
                    "pending_count": counts["pending"],
                    "corrected_count": counts["corrected"],
                }
            )
        return pages

    def _source(self, page_id: str) -> tuple[dict, str, Path]:
        if page_id not in self._pages:
            raise KeyError("página desconhecida")
        path, data, expected_hash = self._pages[page_id]
        if image_sha256(path) != expected_hash:
            raise CorrectionError("sugestões mudaram desde a abertura do servidor")
        image_path = _validate_suggestions(data, self.images_dir)
        return data, expected_hash, image_path

    def _correction_path(self, page_id: str) -> Path:
        if page_id not in self._pages:
            raise KeyError("página desconhecida")
        return self.corrections_dir / f"{page_id}.corrections.json"

    def _load_corrections(self, page_id: str, source: dict, source_hash: str) -> dict:
        path = self._correction_path(page_id)
        if not path.exists():
            return {"revision": 0, "decisions": {}}
        if path.is_symlink():
            raise CorrectionError("correção não pode ser link simbólico")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CorrectionError("JSON de correção inválido") from exc
        if not isinstance(data, dict) or set(data) != {
            "schema_version",
            "kind",
            "image_sha256",
            "suggestions_sha256",
            "revision",
            "decisions",
        }:
            raise CorrectionError("formato de correção inválido")
        if (
            type(data["schema_version"]) is not int
            or data["schema_version"] != SCHEMA_VERSION
            or data["kind"] != "operational_corrections"
            or data["image_sha256"] != source["image"]["sha256"]
            or data["suggestions_sha256"] != source_hash
            or type(data["revision"]) is not int
            or data["revision"] < 1
        ):
            raise CorrectionError("correção incompatível com suas fontes")
        data["decisions"] = validate_decisions(
            data["decisions"],
            len(source["detections"]["staffs"]),
            source["image"]["width"],
            source["image"]["height"],
        )
        return data

    def page(self, page_id: str) -> dict:
        source, source_hash, _ = self._source(page_id)
        corrections = self._load_corrections(page_id, source, source_hash)
        return {
            "id": page_id,
            "name": source["image"]["filename"],
            "image": source["image"],
            "suggestions_sha256": source_hash,
            "revision": corrections["revision"],
            "decisions": corrections["decisions"],
            "view": visual_state(source, corrections["decisions"]),
        }

    def image_path(self, page_id: str) -> Path:
        return self._source(page_id)[2]

    def save(self, page_id: str, payload: object) -> dict:
        if not isinstance(payload, dict) or set(payload) != {
            "base_revision",
            "decisions",
        }:
            raise CorrectionError("envie base_revision e decisions")
        base_revision = payload["base_revision"]
        if type(base_revision) is not int or base_revision < 0:
            raise CorrectionError("base_revision inválida")
        with self._lock:
            source, source_hash, _ = self._source(page_id)
            current = self._load_corrections(page_id, source, source_hash)
            if current["revision"] != base_revision:
                raise RevisionConflict("correções mudaram; recarregue a página")
            decisions = validate_decisions(
                payload["decisions"],
                len(source["detections"]["staffs"]),
                source["image"]["width"],
                source["image"]["height"],
            )
            document = {
                "schema_version": SCHEMA_VERSION,
                "kind": "operational_corrections",
                "image_sha256": source["image"]["sha256"],
                "suggestions_sha256": source_hash,
                "revision": base_revision + 1,
                "decisions": decisions,
            }
            self.corrections_dir.mkdir(parents=True, exist_ok=True)
            target = self._correction_path(page_id)
            if target.is_symlink():
                raise CorrectionError("correção não pode ser link simbólico")
            temporary = None
            try:
                fd, temporary = tempfile.mkstemp(
                    prefix=f".{page_id}.", dir=self.corrections_dir
                )
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(document, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if temporary is not None and Path(temporary).exists():
                    Path(temporary).unlink()
            return self.page(page_id)
