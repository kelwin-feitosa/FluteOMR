"""Cabeças de nota em uma pauta horizontal limpa, sem motor OMR externo."""

from dataclasses import dataclass, replace
from math import ceil, floor

from PIL import Image

from fluteomr.image_io import normalize_image
from fluteomr.music import Duration, Note, Pitch
from fluteomr.staff_detection import Region, Staff


@dataclass(frozen=True)
class NoteheadObservation:
    center_x: int
    center_y: int
    region: Region
    visual_kind: str
    stem_present: bool
    shape_score: float  # fração geométrica heurística, não probabilidade
    diagnostics: tuple[str, ...]


def pitch_from_y(y: float, staff: Staff) -> Pitch | None:
    """Mi4 na linha inferior; cada meio espaçamento avança um grau diatônico."""
    # Interpola entre linhas observadas; o erro de um espaçamento mediano não
    # deve se acumular por toda a altura da pauta. Extrapola só pelo vão externo.
    index = next((i for i in range(4) if y <= staff.lines[i + 1].y), 3)
    top, bottom = staff.lines[index : index + 2]
    gap = bottom.y - top.y
    if gap <= 0:
        return None
    displacement = 8 - 2 * index - 2 * (y - top.y) / gap
    step_index = round(displacement)
    if abs(displacement - step_index) > 0.25 or not -4 <= step_index <= 12:
        return None
    diatonic = 2 + step_index  # C4=0, D4=1, E4=2
    octave_offset, position = divmod(diatonic, 7)
    return Pitch("CDEFGAB"[position], 4 + octave_offset)


def _ink_without_staff(image: Image.Image, staff: Staff, threshold: int) -> bytearray:
    gray = normalize_image(image).convert("L")
    pixels = gray.tobytes()
    ink = bytearray(value <= threshold for value in pixels)
    original = ink.copy()
    width = gray.width
    for line in staff.lines:
        # `thickness` conta linhas inclusivas do raster, não um raio contínuo.
        # Arredondar a borda uma vez evita apagar 3 linhas para um traço de 1 px.
        start = max(0, round(line.y - (line.thickness - 1) / 2))
        end = min(gray.height - 1, start + line.thickness - 1)
        if start == 0 or end == gray.height - 1:
            continue
        for x in range(max(0, line.x_start), min(width - 1, line.x_end) + 1):
            above = any(
                original[(start - 1) * width + nx]
                for nx in range(max(0, x - 1), min(width, x + 2))
            )
            below = any(
                original[(end + 1) * width + nx]
                for nx in range(max(0, x - 1), min(width, x + 2))
            )
            if not (above and below):
                for y in range(start, end + 1):
                    ink[y * width + x] = 0
    return ink


def _shape(
    ink: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    rx: int,
    ry: int,
    core_offsets: tuple[tuple[int, int], ...],
    rim_offsets: tuple[tuple[int, int], ...],
    side_offsets: tuple[tuple[tuple[int, int], ...], ...],
) -> tuple[str, float] | None:
    if x - rx < 0 or x + rx >= width or y - ry < 0 or y + ry >= height:
        return None
    core = sum(ink[(y + dy) * width + x + dx] for dx, dy in core_offsets) / len(
        core_offsets
    )
    rim = sum(ink[(y + dy) * width + x + dx] for dx, dy in rim_offsets) / len(
        rim_offsets
    )
    if core >= 0.58 and rim >= 0.60:
        return "filled", min(core, rim)
    if core <= 0.34 and rim - core / 2 >= 0.44:
        # Uma haste/feixe paralelo pode simular bordas superior e inferior,
        # mas uma cabeça vazada precisa de tinta nos dois lados do anel.
        if all(
            sum(ink[(y + dy) * width + x + dx] for dx, dy in offsets) / len(offsets)
            >= 0.35
            for offsets in side_offsets
        ):
            return "hollow", rim - core / 2
    return None


def _has_stem(
    ink: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    rx: int,
    ry: int,
    spacing: float,
) -> bool:
    reach = round(3.4 * spacing)
    for edge in (-1, 1):
        for offset in range(-1, 2):
            px = x + edge * rx + offset
            if px < 0 or px >= width:
                continue
            for direction in (-1, 1):
                start = y + direction * (ry + 1)
                stop = y + direction * reach
                positions = range(start, stop + direction, direction)
                positions = [py for py in positions if 0 <= py < height]
                if len(positions) < 1.8 * spacing:
                    continue
                count = sum(ink[py * width + px] for py in positions)
                if count >= 1.45 * spacing and count / len(positions) >= 0.38:
                    return True
    return False


def _encloses_hole(
    gray: bytes,
    width: int,
    threshold: int,
    x: int,
    y: int,
    rx: int,
    ry: int,
    spacing: float,
) -> bool:
    """Uma cabeça vazada tem branco encerrado; haste e feixe abertos não têm.

    Usa a imagem anterior à supressão, ampliada no caminho normalizado, para
    preservar o contorno nos cruzamentos da pauta.
    A máscara elíptica amostra tinta, mas não delimita a cavidade: um anel
    inclinado pode ultrapassar seu raio vertical. A busca usa contexto quadrado
    com o raio maior da máscara, sem alterar os critérios de forma ou de haste.
    A linha pode dividir o vazio em duas regiões; basta uma região central
    fechada com área >= 4% do quadrado do espaçamento, sem pixels de borda.
    """
    radius_y = max(rx, ry)
    left, right = max(0, x - rx), min(width - 1, x + rx)
    top, bottom = max(0, y - radius_y), min(len(gray) // width - 1, y + radius_y)
    visited: set[tuple[int, int]] = set()
    for seed in ((x, y), (x, y - max(1, ry // 2)), (x, y + max(1, ry // 2))):
        if seed in visited or gray[seed[1] * width + seed[0]] <= threshold:
            continue
        frontier = [seed]
        visited.add(seed)
        area = 0
        open_boundary = False
        while frontier:
            px, py = frontier.pop()
            area += 1
            if px in (left, right) or py in (top, bottom):
                open_boundary = True
            for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                if (
                    left <= nx <= right
                    and top <= ny <= bottom
                    and (nx, ny) not in visited
                    and gray[ny * width + nx] > threshold
                ):
                    visited.add((nx, ny))
                    frontier.append((nx, ny))
        if not open_boundary and area >= max(1, round(0.04 * spacing**2)):
            return True
    return False


def _compact_horizontal_support(
    ink: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    spacing: float,
) -> bool:
    """Cabeças têm largura finita em várias linhas; um feixe continua além delas.

    Examina a faixa central de meia distância de pauta. Pelo menos 0,15 espaço
    de linhas deve conter um trecho de 0,5 a 1,8 espaço de largura. A linha
    suplementar pode ser mais longa: não se exige compacidade de todas as linhas.
    """
    compact = 0
    radius = max(1, round(0.25 * spacing))
    reach = ceil(3 * spacing)
    for py in range(max(0, y - radius), min(height, y + radius + 1)):
        if not ink[py * width + x]:
            continue
        left = right = x
        while left > 0 and x - left < reach and ink[py * width + left - 1]:
            left -= 1
        while right < width - 1 and right - x < reach and ink[py * width + right + 1]:
            right += 1
        if 0.5 * spacing <= right - left + 1 <= 1.8 * spacing:
            compact += 1
    return compact >= max(2, ceil(0.15 * spacing))


def detect_noteheads(
    image: Image.Image,
    staff: Staff,
    threshold: int,
    measure_left: int,
    measure_right: int,
    *,
    normalize: bool = False,
) -> tuple[NoteheadObservation, ...]:
    """Compara preenchimento central e anel, após suprimir as cinco linhas.

    Busca somente posições diatônicas próximas à pauta e dentro dos limites de
    compasso informados; não usa conteúdo ou referência musical como entrada.
    """
    if not 0 <= measure_left < measure_right < image.width:
        raise ValueError("limites de compasso fora da imagem")
    if normalize and staff.spacing < 16:
        return _normalized_noteheads(
            image, staff, threshold, measure_left, measure_right
        )
    ink = _ink_without_staff(image, staff, threshold)
    gray = normalize_image(image).convert("L").tobytes()
    spacing = staff.spacing
    rx = max(3, round(0.65 * spacing))
    ry = max(2, round(0.42 * spacing))
    core_offsets = tuple(
        (dx, dy)
        for dy in range(-ry, ry + 1)
        for dx in range(-rx, rx + 1)
        if (dx / rx) ** 2 + (dy / ry) ** 2 <= 0.30
    )
    rim_offsets = tuple(
        (dx, dy)
        for dy in range(-ry, ry + 1)
        for dx in range(-rx, rx + 1)
        if 0.55 <= (dx / rx) ** 2 + (dy / ry) ** 2 <= 1.15
    )
    side_offsets = tuple(
        tuple(
            (dx, dy)
            for dx, dy in rim_offsets
            if dx * side > 0 and abs(dx) >= 0.55 * rx and abs(dy) <= 0.6 * ry
        )
        for side in (-1, 1)
    )
    candidates = []
    for degree in range(-4, 13):
        center = staff.lines[-1].y - degree * spacing / 2
        for y in range(
            round(center - 0.12 * spacing), round(center + 0.12 * spacing) + 1
        ):
            for x in range(measure_left + rx, measure_right - rx + 1):
                match = _shape(
                    ink,
                    image.width,
                    image.height,
                    x,
                    y,
                    rx,
                    ry,
                    core_offsets,
                    rim_offsets,
                    side_offsets,
                )
                if match is None:
                    continue
                visual_kind, score = match
                if visual_kind == "filled" and not _compact_horizontal_support(
                    ink, image.width, image.height, x, y, spacing
                ):
                    continue
                if visual_kind == "hollow" and not _encloses_hole(
                    gray, image.width, threshold, x, y, rx, ry, spacing
                ):
                    continue
                stem = _has_stem(ink, image.width, image.height, x, y, rx, ry, spacing)
                candidates.append(
                    NoteheadObservation(
                        x,
                        y,
                        Region(x - rx, y - ry, x + rx, y + ry),
                        visual_kind,
                        stem,
                        score,
                        () if stem else ("stem_not_confirmed",),
                    )
                )
    return _deduplicate_candidates(candidates, spacing)


def _normalized_noteheads(
    image: Image.Image,
    staff: Staff,
    threshold: int,
    left: int,
    right: int,
) -> tuple[NoteheadObservation, ...]:
    """Recupera anéis vazados em região local, preservando candidatos nativos.

    A máscara fixa fica muito quantizada abaixo de 16 px/espaço. A interpolação
    bilinear estabiliza anéis; não recria evidência que não exista. Ela também
    pode criar falsas cabeças preenchidas junto a feixes. Por isso os candidatos
    nativos são mantidos, e só anéis novos com cavidade e haste no raster original
    são adicionados. Não se usa o fechamento rítmico para escolher candidatos.
    """
    spacing = staff.spacing
    native = detect_noteheads(image, staff, threshold, left, right)
    x0, y0 = (
        max(0, floor(left - 2 * spacing)),
        max(0, floor(staff.lines[0].y - 7 * spacing)),
    )
    x1, y1 = (
        min(image.width, ceil(right + 2 * spacing) + 1),
        min(image.height, ceil(staff.lines[-1].y + 7 * spacing) + 1),
    )
    crop = normalize_image(image).convert("L").crop((x0, y0, x1, y1))
    scale = 20 / spacing
    width, height = round(crop.width * scale), round(crop.height * scale)
    enlarged = crop.resize((width, height), Image.Resampling.BILINEAR)
    sx, sy = width / crop.width, height / crop.height
    lines = tuple(
        replace(
            line,
            x_start=max(0, round((line.x_start - x0) * sx)),
            x_end=min(width - 1, round((line.x_end - x0) * sx)),
            y=(line.y - y0) * sy,
            thickness=max(1, round(line.thickness * sy)),
        )
        for line in staff.lines
    )
    local_staff = Staff(
        lines,
        spacing * sy,
        Region(lines[0].x_start, lines[0].y, lines[0].x_end, lines[-1].y),
    )
    heads = detect_noteheads(
        enlarged,
        local_staff,
        threshold,
        round((left - x0) * sx),
        min(width - 1, round((right - x0) * sx)),
    )
    mapped = tuple(
        replace(
            head,
            center_x=round(head.center_x / sx + x0),
            center_y=round(head.center_y / sy + y0),
            region=Region(
                max(0, round(head.region.left / sx + x0)),
                max(0, round(head.region.top / sy + y0)),
                min(image.width - 1, round(head.region.right / sx + x0)),
                min(image.height - 1, round(head.region.bottom / sy + y0)),
            ),
            diagnostics=(*head.diagnostics, "staff_space_normalized"),
        )
        for head in heads
        if head.visual_kind == "hollow"
    )
    gray = normalize_image(image).convert("L").tobytes()
    ink = _ink_without_staff(image, staff, threshold)
    recovered = []
    for head in mapped:
        # Reaplica a sonda nativa: dividir uma caixa arredondada podia perder
        # outra linha de pixels no contorno inferior de uma mínima pequena.
        rx = max(3, round(0.65 * spacing))
        ry = max(2, round(0.42 * spacing))
        if (
            head.center_x - rx < 0
            or head.center_x + rx >= image.width
            or head.center_y - ry < 0
            or head.center_y + ry >= image.height
        ):
            continue
        if not _encloses_hole(
            gray,
            image.width,
            threshold,
            head.center_x,
            head.center_y,
            rx,
            ry,
            spacing,
        ) or not _has_stem(
            ink,
            image.width,
            image.height,
            head.center_x,
            head.center_y,
            rx,
            ry,
            spacing,
        ):
            continue
        if any(
            abs(head.center_x - existing.center_x) < 0.9 * spacing
            and abs(head.center_y - existing.center_y) < 1.1 * spacing
            for existing in (*native, *recovered)
        ):
            continue
        recovered.append(
            replace(
                head,
                stem_present=True,
                diagnostics=tuple(
                    d for d in head.diagnostics if d != "stem_not_confirmed"
                ),
            )
        )
    return tuple(sorted((*native, *recovered), key=lambda h: h.center_x))


def _deduplicate_candidates(
    candidates: list[NoteheadObservation], spacing: float
) -> tuple[NoteheadObservation, ...]:
    """Une sondas da mesma cabeça; mantém eventos próximos em `x` e grau distinto."""
    chosen = []
    for candidate in sorted(
        candidates, key=lambda c: (c.stem_present, c.shape_score), reverse=True
    ):
        if any(
            abs(candidate.center_x - previous.center_x) < 0.9 * spacing
            and (
                abs(candidate.center_y - previous.center_y) < 0.65 * spacing
                or (
                    abs(candidate.center_x - previous.center_x) < 0.35 * spacing
                    and abs(candidate.center_y - previous.center_y) < 1.1 * spacing
                )
            )
            for previous in chosen
        ):
            continue
        chosen.append(candidate)
    return tuple(sorted(chosen, key=lambda c: c.center_x))


def notes_from_observations(
    observations: tuple[NoteheadObservation, ...], staff: Staff, staff_index: int
) -> tuple[Note, ...]:
    notes = []
    for head in observations:
        pitch = pitch_from_y(head.center_y, staff)
        duration = (
            Duration("quarter" if head.visual_kind == "filled" else "half")
            if head.stem_present
            else None
        )
        notes.append(
            Note(
                pitch,
                duration,
                head.region,
                staff_index,
                head.visual_kind,
                head.diagnostics,
                "image" if pitch else "unknown",
                "image" if duration else "unknown",
                f"s{staff_index}-h{head.center_x}-{head.center_y}",
            )
        )
    return tuple(notes)
