"""Evidência geométrica de bandeirolas e feixes de colcheias/semicolcheias.

Apenas grupos completos de dois traços separados são reconhecidos como
semicolcheias; feixes secundários parciais permanecem inconclusivos.
"""

from dataclasses import dataclass
from statistics import median
from typing import Literal

from PIL import Image

from fluteomr.image_io import normalize_image
from fluteomr.music import BeamPosition
from fluteomr.notes import NoteheadObservation, _ink_without_staff
from fluteomr.staff_detection import Region, Staff
from fluteomr.symbols import BarlineCandidate, StemCandidate, head_id


@dataclass(frozen=True)
class RhythmEvidence:
    head_id: str
    kind: Literal["flag", "beam", "double_beam"]
    region: Region
    status: Literal["accepted", "inconclusive"]
    beam_position: Literal["begin", "continue", "end"] | None = None
    reason: str = ""
    # Níveis explícitos só aparecem quando a geometria sustenta grupo misto.
    beam_levels: tuple[tuple[int, BeamPosition], ...] = ()


def _stem_tip(
    pixels,
    height: int,
    head: NoteheadObservation,
    stem: StemCandidate,
    spacing: float,
    threshold: int,
) -> tuple[int, int]:
    x = stem.region.left
    direction = -1 if x > head.center_x else 1
    ry = (head.region.bottom - head.region.top) // 2
    start = head.center_y + direction * max(1, ry - 2)
    last = start
    blank = 0
    for distance in range(round(4.5 * spacing)):
        y = start + direction * distance
        if y < 0 or y >= height:
            break
        if pixels[x, y] <= threshold:
            last = y
            blank = 0
        else:
            blank += 1
            if blank > max(2, round(0.13 * spacing)):
                break
    return x, last


def _stripe_support(
    ink: bytearray,
    width: int,
    height: int,
    a: tuple[int, int],
    b: tuple[int, int],
    radius: int,
    offset: int = 0,
) -> tuple[float, int]:
    left, right = sorted((a, b))
    if right[0] - left[0] <= 2 * radius:
        return 0.0, 0
    hits = 0
    samples = 0
    gap = longest_gap = 0
    for x in range(left[0] + radius, right[0] - radius + 1):
        y = (
            round(left[1] + (right[1] - left[1]) * (x - left[0]) / (right[0] - left[0]))
            + offset
        )
        samples += 1
        has_ink = any(
            0 <= row < height and ink[row * width + x]
            for row in range(y - radius, y + radius + 1)
        )
        if has_ink:
            hits += 1
            gap = 0
        else:
            gap += 1
            longest_gap = max(longest_gap, gap)
    return (hits / samples if samples else 0.0), longest_gap


def _adaptive_secondary_profile(
    ink: bytearray,
    width: int,
    height: int,
    a: tuple[int, int],
    b: tuple[int, int],
    direction: int,
    spacing: float,
) -> tuple[str, int | None]:
    """Busca DUAS bandas paralelas completas separadas por um vale vazio.

    Experimentação opcional: a distância entre os centros é determinada
    pela própria tinta, e não pelo offset fixo do reconhecedor estável.
    Não atribui nota nem duração sem verificar o grupo musical inteiro.
    """
    minimum_distance = max(3, round(0.34 * spacing))
    maximum_offset = max(minimum_distance + 2, round(1.35 * spacing))
    search_primary = max(2, round(0.38 * spacing))
    thin_radius = 0
    supports = [
        _stripe_support(
            ink,
            width,
            height,
            a,
            b,
            thin_radius,
            -direction * offset,
        )
        for offset in range(maximum_offset + 1)
    ]
    primary_offset = max(
        range(search_primary + 1),
        key=lambda idx: supports[idx][0],
    )
    if supports[primary_offset][0] < 0.70:
        return "ambiguous", None
    secondary = range(primary_offset + minimum_distance, maximum_offset + 1)
    strongest = max(
        (supports[index][0] for index in secondary), default=0.0
    )
    # Cada faixa deve ser contínua ao longo da distância entre hastes.
    for index in sorted(
        secondary, key=lambda item: supports[item][0], reverse=True
    ):
        coverage, gap = supports[index]
        if coverage < 0.78 or gap > 1.2 * spacing:
            break
        if index - primary_offset < minimum_distance:
            continue
        # Cada pico precisa estar separado por pelo menos uma linha
        # transversal com pouca tinta, longe das duas bandas.
        valley = min(
            (supports[pos][0] for pos in range(primary_offset + 1, index)),
            default=1.0,
        )
        if valley <= 0.30:
            return "confirmed", index - primary_offset
    if strongest >= 0.50:
        return "ambiguous", None
    if strongest >= 0.18:
        return "weak", None
    return "absent", None


def _flag_evidence(
    ink: bytearray,
    width: int,
    height: int,
    tip: tuple[int, int],
    direction: int,
    spacing: float,
) -> tuple[Literal["accepted", "inconclusive"], int] | None:
    """Busca curva lateral contínua que progride da ponta rumo à cabeça."""
    x, y = tip
    start = y - direction * round(0.15 * spacing)
    end = y - direction * round(1.5 * spacing)
    low, high = max(0, min(start, end)), min(height - 1, max(start, end))
    if low > high:
        return None
    choices = []
    # Algumas fontes desenham a curva da haste descendente à direita; outras
    # usam o lado esquerdo. Ambos precisam de tinta contínua e progressão.
    for side in (1,) if direction == -1 else (-1, 1):
        samples = []
        for distance in range(max(2, round(0.22 * spacing)), round(0.9 * spacing) + 1):
            probe_x = x + side * distance
            if not 0 <= probe_x < width:
                continue
            rows = [row for row in range(low, high + 1) if ink[row * width + probe_x]]
            samples.append((distance, median(rows) if rows else None))
        if not samples:
            continue
        present = [(distance, row) for distance, row in samples if row is not None]
        coverage = len(present) / len(samples)
        if len(present) < 2:
            continue
        extent = present[-1][0] - present[0][0]
        quarter = max(1, len(present) // 4)
        near = median(row for _, row in present[:quarter])
        far = median(row for _, row in present[-quarter:])
        progression = (far - near) * -direction
        if (
            coverage >= 0.65
            and extent >= 0.45 * spacing
            and progression >= 0.2 * spacing
        ):
            choices.append(("accepted", side, coverage))
        elif (
            coverage >= 0.25
            and extent >= 0.25 * spacing
            and progression >= 0.1 * spacing
        ):
            choices.append(("inconclusive", side, coverage))
    if not choices:
        return None
    accepted = [choice for choice in choices if choice[0] == "accepted"]
    if len(accepted) > 1:
        return "inconclusive", max(accepted, key=lambda item: item[2])[1]
    best = max(accepted or choices, key=lambda item: item[2])
    return best[0], best[1]


def detect_rhythm_evidence(
    image: Image.Image,
    staff: Staff,
    threshold: int,
    heads: tuple[NoteheadObservation, ...],
    stems: tuple[StemCandidate, ...],
    staff_index: int = 0,
    barlines: tuple[BarlineCandidate, ...] = (),
    adaptive_secondary: bool = False,
) -> tuple[RhythmEvidence, ...]:
    """Liga marcas às hastes; exige segundo feixe contínuo em todo o grupo."""
    if not stems:
        return ()
    pixels = normalize_image(image).convert("L").load()
    ink = _ink_without_staff(image, staff, threshold)
    by_id = {head_id(head, staff_index): head for head in heads}
    linked = [(stem, by_id[stem.head_id]) for stem in stems if stem.head_id in by_id]
    tips = {
        stem.id: _stem_tip(pixels, image.height, head, stem, staff.spacing, threshold)
        for stem, head in linked
    }
    direction = {
        stem.id: -1 if stem.region.left > head.center_x else 1 for stem, head in linked
    }
    connections: dict[str, set[str]] = {stem.id: set() for stem, _ in linked}
    secondary_connections: dict[str, set[str]] = {stem.id: set() for stem, _ in linked}
    ambiguous_secondary: set[str] = set()
    weak_secondary: set[str] = set()
    radius = max(2, round(0.32 * staff.spacing))
    for (first, first_head), (second, second_head) in zip(
        linked, linked[1:], strict=False
    ):
        if first_head.visual_kind != "filled" or second_head.visual_kind != "filled":
            continue
        if direction[first.id] != direction[second.id]:
            continue
        a, b = tips[first.id], tips[second.id]
        if abs(b[0] - a[0]) < 1.2 * staff.spacing:
            continue
        if any(
            bar.status == "accepted" and min(a[0], b[0]) < bar.x < max(a[0], b[0])
            for bar in barlines
        ):
            continue
        if abs(b[1] - a[1]) > 0.8 * abs(b[0] - a[0]):
            continue
        support, longest_gap = _stripe_support(
            ink, image.width, image.height, a, b, radius
        )
        if support < 0.78 or longest_gap > 1.2 * staff.spacing:
            continue
        if adaptive_secondary:
            status, _separation = _adaptive_secondary_profile(
                ink,
                image.width,
                image.height,
                a,
                b,
                direction[first.id],
                staff.spacing,
            )
            if status == "confirmed":
                secondary_connections[first.id].add(second.id)
                secondary_connections[second.id].add(first.id)
            elif status == "ambiguous":
                ambiguous_secondary.update((first.id, second.id))
            elif status == "weak":
                weak_secondary.update((first.id, second.id))
        else:
            offset = -direction[first.id] * round(0.95 * staff.spacing)
            secondary_support, secondary_gap = _stripe_support(
                ink,
                image.width,
                image.height,
                a,
                b,
                max(1, radius // 2),
                offset,
            )
            if secondary_support >= 0.78 and secondary_gap <= 1.2 * staff.spacing:
                # Um feixe grosso ou uma faixa mesclada não são dois feixes.
                # Exigir um vale claro entre os dois traços amostrados, longe
                # das hastes, evita promover paralelas que se tocam.
                midpoint_support, _ = _stripe_support(
                    ink,
                    image.width,
                    image.height,
                    a,
                    b,
                    max(1, round(0.08 * staff.spacing)),
                    -direction[first.id] * round(0.5 * staff.spacing),
                )
                if midpoint_support <= 0.35:
                    secondary_connections[first.id].add(second.id)
                    secondary_connections[second.id].add(first.id)
                else:
                    ambiguous_secondary.update((first.id, second.id))
            elif secondary_support >= 0.55:
                # Uma marca secundária interrompida pode ser um feixe curto
                # (hook). Não exportar a relação como colcheia sem revisão.
                ambiguous_secondary.update((first.id, second.id))
            elif secondary_support >= 0.18:
                # Só bloqueia INFERÊNCIA DE GRUPO MISTO caso haja também um
                # segundo feixe confirmado em outro par desse mesmo grupo.
                # Evita alterar grupos simples que antes não tinham evidência.
                weak_secondary.update((first.id, second.id))
        connections[first.id].add(second.id)
        connections[second.id].add(first.id)
    groups = {}
    accepted_double: set[str] = set()
    accepted_mixed: set[str] = set()
    uncertain_double: set[str] = set()
    uncertain_reason: dict[str, str] = {}
    for stem, _ in linked:
        if stem.id in groups or not connections[stem.id]:
            continue
        members = {stem.id}
        frontier = [stem.id]
        while frontier:
            current = frontier.pop()
            for neighbor in connections[current] - members:
                members.add(neighbor)
                frontier.append(neighbor)
        group = frozenset(members)
        groups.update({member: group for member in group})
        secondary_present = any(secondary_connections[member] for member in group)
        if group & ambiguous_secondary:
            uncertain_double.update(group)
            uncertain_reason.update(
                (member, "secondary_stripe_ambiguous") for member in group
            )
        elif secondary_present:
            # Um segundo feixe só é suficiente para as hastes que toca.
            # Os outros pares devem estar CLARAMENTE sem uma segunda linha.
            # Traços fracos podem ser hooks, interrupções ou imagem degradada.
            if group & weak_secondary:
                uncertain_double.update(group)
                uncertain_reason.update(
                    (member, "weak_secondary_stripe") for member in group
                )
            elif all(
                secondary_connections[member] == connections[member]
                and 1 <= len(connections[member]) <= 2
                for member in group
            ):
                accepted_double.update(group)
            elif all(
                len(connections[member]) <= 2
                and secondary_connections[member] <= connections[member]
                for member in group
            ):
                accepted_mixed.update(group)
            else:
                uncertain_double.update(group)
                uncertain_reason.update(
                    (member, "secondary_group_inconsistent") for member in group
                )
    evidence = []
    for index, (stem, head) in enumerate(linked):
        tip = tips[stem.id]
        group = groups.get(stem.id)
        if group:
            group_tips = [tips[member] for member in group]
            region = Region(
                max(0, min(x for x, _ in group_tips) - radius),
                max(0, min(y for _, y in group_tips) - radius),
                min(image.width - 1, max(x for x, _ in group_tips) + radius),
                min(image.height - 1, max(y for _, y in group_tips) + radius),
            )
        else:
            flag = (
                _flag_evidence(
                    ink,
                    image.width,
                    image.height,
                    tip,
                    direction[stem.id],
                    staff.spacing,
                )
                if head.visual_kind == "filled"
                else None
            )
            side = flag[1] if flag else 1
            end_x = tip[0] + side * round(staff.spacing)
            end_y = tip[1] - direction[stem.id] * round(1.5 * staff.spacing)
            region = Region(
                max(0, min(tip[0], end_x)),
                max(0, min(tip[1], end_y)),
                min(image.width - 1, max(tip[0], end_x)),
                min(image.height - 1, max(tip[1], end_y)),
            )
        if connections[stem.id]:
            left = index > 0 and linked[index - 1][0].id in connections[stem.id]
            right = (
                index + 1 < len(linked)
                and linked[index + 1][0].id in connections[stem.id]
            )
            position = "continue" if left and right else "end" if left else "begin"
            if stem.id in accepted_mixed:
                secondary_left = (
                    index > 0
                    and linked[index - 1][0].id in secondary_connections[stem.id]
                )
                secondary_right = (
                    index + 1 < len(linked)
                    and linked[index + 1][0].id in secondary_connections[stem.id]
                )
                secondary_position = (
                    "continue"
                    if secondary_left and secondary_right
                    else "end"
                    if secondary_left
                    else "begin"
                    if secondary_right
                    else None
                )
                levels: tuple[tuple[int, BeamPosition], ...] = ((1, position),)
                if secondary_position is not None:
                    levels = (*levels, (2, secondary_position))
                evidence.append(
                    RhythmEvidence(
                        stem.head_id,
                        "double_beam" if secondary_position else "beam",
                        region,
                        "accepted",
                        position,
                        "verified_partial_secondary_group",
                        beam_levels=levels,
                    )
                )
            elif stem.id in accepted_double:
                evidence.append(
                    RhythmEvidence(
                        stem.head_id,
                        "double_beam",
                        region,
                        "accepted",
                        position,
                        "two_separated_continuous_beams",
                    )
                )
            elif stem.id in uncertain_double:
                evidence.append(
                    RhythmEvidence(
                        stem.head_id,
                        "double_beam",
                        region,
                        "inconclusive",
                        reason=uncertain_reason.get(
                            stem.id, "partial_or_ambiguous_double_beam"
                        ),
                    )
                )
            else:
                evidence.append(
                    RhythmEvidence(
                        stem.head_id,
                        "beam",
                        region,
                        "accepted",
                        position,
                        "continuous_single_beam",
                    )
                )
        elif flag:
            evidence.append(
                RhythmEvidence(
                    stem.head_id,
                    "flag",
                    region,
                    flag[0],
                    reason=(
                        "curved_flag_geometry"
                        if flag[0] == "accepted"
                        else "weak_flag_geometry"
                    ),
                )
            )
    return tuple(evidence)
