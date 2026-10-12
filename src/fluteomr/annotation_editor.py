"""Edição local de rascunhos; nenhuma operação promove referência a validada."""

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path

from fluteomr.annotations import (
    AnnotationError,
    load_reference,
    validate_reference,
    verify_image,
)


def image_to_canvas(x: float, y: float, zoom: float) -> tuple[float, float]:
    """Converte coordenadas da imagem para o canvas rolável."""
    if zoom <= 0:
        raise ValueError("zoom deve ser positivo")
    return x * zoom, y * zoom


def canvas_to_image(
    x: float, y: float, zoom: float, width: int, height: int
) -> tuple[int, int]:
    """Arredonda e limita ao último pixel válido da imagem."""
    if zoom <= 0:
        raise ValueError("zoom deve ser positivo")
    return (
        min(width - 1, max(0, round(x / zoom))),
        min(height - 1, max(0, round(y / zoom))),
    )


def drag_box(start: tuple[int, int], end: tuple[int, int]) -> dict:
    """Cria caixa inclusiva; um clique isolado não forma região."""
    left, right = sorted((start[0], end[0]))
    top, bottom = sorted((start[1], end[1]))
    if left == right or top == bottom:
        raise AnnotationError("arraste para criar uma caixa com largura e altura")
    return dict(left=left, top=top, right=right, bottom=bottom)


def move_box(box: dict, dx: int, dy: int, width: int, height: int) -> dict:
    """Move uma caixa inteira, prendendo-a às bordas sem deformá-la."""
    dx = max(-box["left"], min(dx, width - 1 - box["right"]))
    dy = max(-box["top"], min(dy, height - 1 - box["bottom"]))
    return {key: box[key] + (dx if key in ("left", "right") else dy) for key in box}


def resize_box(box: dict, right: int, bottom: int, width: int, height: int) -> dict:
    """Redimensiona pela alça inferior direita, mantendo lados positivos."""
    return {
        **box,
        "right": min(width - 1, max(box["left"] + 1, right)),
        "bottom": min(height - 1, max(box["top"] + 1, bottom)),
    }


def _fresh_id(items: list[dict], prefix: str) -> str:
    used = {item["id"] for item in items}
    index = 0
    while f"{prefix}{index}" in used:
        index += 1
    return f"{prefix}{index}"


def _positive_box(box: dict | None) -> None:
    if box is not None and (box["right"] <= box["left"] or box["bottom"] <= box["top"]):
        raise AnnotationError("caixa deve ter largura e altura positivas")


def next_pending_clef(data: dict, current: str | None) -> str | None:
    """Próxima clave desconhecida, sem retornar o item atual nem alterar o rascunho."""
    ids = [staff["id"] for staff in data["staffs"]]
    if not ids:
        return None
    start = ids.index(current) if current in ids else -1
    for offset in range(1, len(ids) + 1):
        candidate = ids[(start + offset) % len(ids)]
        if candidate != current and any(
            clef["staff_id"] == candidate and clef["state"] == "unknown"
            for clef in data["clefs"]
        ):
            return candidate
    return None


def hit_box(
    point: tuple[int, int], boxes: list[tuple[str, str, dict]]
) -> tuple[str, str] | None:
    """Seleciona a menor região sobreposta; claves têm prioridade em empates."""
    matches = [
        (kind, item_id, box)
        for kind, item_id, box in boxes
        if box["left"] <= point[0] <= box["right"]
        and box["top"] <= point[1] <= box["bottom"]
    ]
    if not matches:
        return None
    kind, item_id, _ = min(
        matches,
        key=lambda entry: (
            (entry[2]["right"] - entry[2]["left"])
            * (entry[2]["bottom"] - entry[2]["top"]),
            0 if entry[0] == "clefs" else 1,
        ),
    )
    return kind, item_id


class AnnotationEditor:
    """Documento editável com validação transacional e salvamento atômico."""

    def __init__(self, path: Path, image_dir: Path):
        self.path = Path(path)
        self.image_dir = Path(image_dir)
        self.data = load_reference(self.path)
        verify_image(self.data, self.image_dir)
        self._saved = copy.deepcopy(self.data)
        self._source_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()

    @property
    def dirty(self) -> bool:
        return self.data != self._saved

    @property
    def editable(self) -> bool:
        return self.data["review"]["status"] == "draft"

    @property
    def size(self) -> tuple[int, int]:
        image = self.data["image"]
        return image["width"], image["height"]

    def _change(self, change) -> None:
        if not self.editable:
            raise PermissionError("referência validada é somente leitura")
        candidate = copy.deepcopy(self.data)
        change(candidate)
        validate_reference(candidate)
        self.data = candidate

    def revert(self) -> None:
        self.data = copy.deepcopy(self._saved)

    def check(self) -> None:
        validate_reference(self.data)
        verify_image(self.data, self.image_dir)

    def update_page(self, *, split: str, coverage: dict[str, str]) -> None:
        def change(data):
            data["split"] = split
            data["coverage"] = coverage.copy()

        self._change(change)

    def item(self, kind: str, item_id: str) -> dict:
        key = "staff_id" if kind == "clefs" else "id"
        return next(item for item in self.data[kind] if item[key] == item_id)

    def box(self, kind: str, item_id: str) -> dict | None:
        if kind != "systems":
            return self.item(kind, item_id)["region"]
        members = set(self.item("systems", item_id)["staff_ids"])
        boxes = [
            staff["region"]
            for staff in self.data["staffs"]
            if staff["id"] in members and staff["region"] is not None
        ]
        if not boxes:
            return None
        return {
            "left": min(box["left"] for box in boxes),
            "top": min(box["top"] for box in boxes),
            "right": max(box["right"] for box in boxes),
            "bottom": max(box["bottom"] for box in boxes),
        }

    def update_staff(
        self,
        item_id: str,
        *,
        region: dict | None,
        lines: list[dict] | None,
        review_state: str,
    ) -> None:
        _positive_box(region)

        def change(data):
            staff = next(item for item in data["staffs"] if item["id"] == item_id)
            staff.update(region=region, lines=lines, review_state=review_state)
            data["staffs"].sort(
                key=lambda item: (
                    item["region"]["top"] if item["region"] else float("inf")
                )
            )
            for order, member in enumerate(data["staffs"]):
                member["order"] = order

        self._change(change)

    def update_system(
        self,
        item_id: str,
        *,
        staff_ids: list[str],
        review_state: str,
        partial_visible: bool,
    ) -> None:
        def change(data):
            system = next(item for item in data["systems"] if item["id"] == item_id)
            system.update(
                staff_ids=staff_ids,
                review_state=review_state,
                partial_visible=partial_visible,
            )

        self._change(change)

    def update_clef(
        self, item_id: str, *, state: str, kind: str | None, region: dict | None
    ) -> None:
        _positive_box(region)

        def change(data):
            clef = next(item for item in data["clefs"] if item["staff_id"] == item_id)
            clef.update(state=state, kind=kind, region=region)

        self._change(change)

    def confirm_treble_suggestion(self, staff_id: str, prediction: dict | None) -> None:
        """Aceita somente uma sugestão geométrica existente por ação explícita."""
        if not prediction or prediction.get("status") != "detected":
            raise AnnotationError("não há sugestão de clave aceita para esta pauta")
        box = prediction.get("region")
        if box is None:
            raise AnnotationError("a sugestão não contém uma região")
        self.update_clef(staff_id, state="present", kind="treble", region=box.copy())

    def review_clef(self, staff_id: str, kind: str, box: dict) -> None:
        """Registra uma região desenhada e o tipo escolhido pelo anotador."""
        self.update_clef(staff_id, state="present", kind=kind, region=box.copy())

    def set_box(
        self, kind: str, item_id: str, box: dict, *, move: bool = False
    ) -> None:
        """A pauta movida leva suas linhas junto; sistema não possui caixa própria."""
        if kind == "systems":
            raise AnnotationError("edite as pautas ou os membros do sistema")
        item = self.item(kind, item_id)
        if kind == "clefs":
            if item["state"] != "present":
                raise AnnotationError("marque a clave como presente antes de desenhar")
            self.update_clef(
                item_id, state=item["state"], kind=item["kind"], region=box
            )
            return
        lines = copy.deepcopy(item["lines"])
        old = item["region"]
        if move and old is not None and lines is not None:
            dx, dy = box["left"] - old["left"], box["top"] - old["top"]
            for line in lines:
                line["x_start"] += dx
                line["x_end"] += dx
                line["y"] += dy
        self.update_staff(
            item_id, region=box, lines=lines, review_state=item["review_state"]
        )

    def add_staff(self, box: dict) -> str:
        _positive_box(box)
        item_id = _fresh_id(self.data["staffs"], "s")

        def change(data):
            data["staffs"].append(
                {
                    "id": item_id,
                    "order": len(data["staffs"]),
                    "review_state": "unknown",
                    "region": box,
                    "lines": None,
                }
            )
            data["staffs"].sort(key=lambda item: item["region"]["top"])
            for order, member in enumerate(data["staffs"]):
                member["order"] = order
            data["clefs"].append(
                {"staff_id": item_id, "state": "unknown", "kind": None, "region": None}
            )
            data["coverage"] = dict.fromkeys(data["coverage"], "unknown")

        self._change(change)
        return item_id

    def add_system(self, staff_ids: list[str]) -> str:
        item_id = _fresh_id(self.data["systems"], "sys")

        def change(data):
            data["systems"].append(
                {
                    "id": item_id,
                    "order": len(data["systems"]),
                    "staff_ids": staff_ids,
                    "review_state": "uncertain",
                    "partial_visible": False,
                }
            )
            data["coverage"]["systems"] = "unknown"

        self._change(change)
        return item_id

    def add_clef(self, staff_id: str) -> None:
        def change(data):
            data["clefs"].append(
                {"staff_id": staff_id, "state": "unknown", "kind": None, "region": None}
            )
            data["coverage"]["clefs"] = "unknown"

        self._change(change)

    def delete(self, kind: str, item_id: str) -> None:
        def change(data):
            key = "staff_id" if kind == "clefs" else "id"
            data[kind] = [item for item in data[kind] if item[key] != item_id]
            if kind == "staffs":
                data["clefs"] = [
                    item for item in data["clefs"] if item["staff_id"] != item_id
                ]
                for system in data["systems"]:
                    system["staff_ids"] = [
                        member for member in system["staff_ids"] if member != item_id
                    ]
                data["systems"] = [
                    system for system in data["systems"] if system["staff_ids"]
                ]
                data["coverage"] = dict.fromkeys(data["coverage"], "unknown")
            else:
                data["coverage"][kind] = "unknown"
            for collection in ("staffs", "systems"):
                for order, item in enumerate(data[collection]):
                    item["order"] = order

        self._change(change)

    def save(self, target: Path | None = None) -> Path:
        """Valida e troca arquivo temporário; nunca sobrescreve outra referência."""
        if not self.editable:
            raise PermissionError("referência validada é somente leitura")
        self.check()
        target = self.path if target is None else Path(target)
        if target.exists():
            if target.resolve() != self.path.resolve():
                raise FileExistsError(f"destino já existe: {target}")
            current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            if current_hash != self._source_hash:
                raise AnnotationError("arquivo mudou no disco desde a abertura")
        payload = json.dumps(self.data, ensure_ascii=False, indent=2) + "\n"
        temp_name = None
        try:
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{target.name}.", dir=target.parent
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, target)
        finally:
            if temp_name is not None and Path(temp_name).exists():
                Path(temp_name).unlink()
        self.path = target
        self._saved = copy.deepcopy(self.data)
        self._source_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        return target
