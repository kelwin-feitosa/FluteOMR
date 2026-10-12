"""Métricas puras: referências e predições são dados, não detectores."""

from itertools import combinations
from statistics import mean, median

NOT_EVALUABLE = "not_evaluable"


def _box_overlap(a: dict, b: dict) -> float:
    left = max(a["left"], b["left"])
    right = min(a["right"], b["right"])
    return max(0.0, right - left + 1)


def _iou(a: dict, b: dict) -> float:
    x = _box_overlap(a, b)
    y = max(0.0, min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]) + 1)
    intersection = x * y
    area_a = (a["right"] - a["left"] + 1) * (a["bottom"] - a["top"] + 1)
    area_b = (b["right"] - b["left"] + 1) * (b["bottom"] - b["top"] + 1)
    return intersection / (area_a + area_b - intersection)


def _spacing(staff: dict) -> float:
    lines = staff.get("lines")
    if lines is not None:
        return median(lines[i + 1]["y"] - lines[i]["y"] for i in range(4))
    box = staff["region"]
    return max(1.0, (box["bottom"] - box["top"]) / 4)


def _eligible(ref: dict, pred: dict) -> float | None:
    reference, predicted = ref["region"], pred["region"]
    spacing = _spacing(ref)
    center_delta = abs(
        (reference["top"] + reference["bottom"]) / 2
        - (predicted["top"] + predicted["bottom"]) / 2
    )
    ref_height = reference["bottom"] - reference["top"] + 1
    pred_height = predicted["bottom"] - predicted["top"] + 1
    shorter = min(
        reference["right"] - reference["left"] + 1,
        predicted["right"] - predicted["left"] + 1,
    )
    overlap = _box_overlap(reference, predicted) / shorter
    if (
        center_delta > 0.75 * spacing
        or not 0.5 <= pred_height / ref_height <= 1.8
        or overlap < 0.5
    ):
        return None
    return center_delta / spacing + (1 - overlap)


def _assignment(costs: list[list[float]]) -> list[int]:
    """Atribuição mínima retangular (Hungarian); colunas dummy permitem FN."""
    rows = len(costs)
    if not rows:
        return []
    columns = len(costs[0])
    u = [0.0] * (rows + 1)
    v = [0.0] * (columns + 1)
    p = [0] * (columns + 1)
    way = [0] * (columns + 1)
    for row in range(1, rows + 1):
        p[0] = row
        column = 0
        minimum = [float("inf")] * (columns + 1)
        used = [False] * (columns + 1)
        while True:
            used[column] = True
            active = p[column]
            delta = float("inf")
            next_column = 0
            for candidate in range(1, columns + 1):
                if used[candidate]:
                    continue
                reduced = costs[active - 1][candidate - 1] - u[active] - v[candidate]
                if reduced < minimum[candidate]:
                    minimum[candidate] = reduced
                    way[candidate] = column
                if minimum[candidate] < delta:
                    delta = minimum[candidate]
                    next_column = candidate
            for candidate in range(columns + 1):
                if used[candidate]:
                    u[p[candidate]] += delta
                    v[candidate] -= delta
                else:
                    minimum[candidate] -= delta
            column = next_column
            if p[column] == 0:
                break
        while True:
            previous = way[column]
            p[column] = p[previous]
            column = previous
            if column == 0:
                break
    result = [-1] * rows
    for column in range(1, columns + 1):
        if p[column]:
            result[p[column] - 1] = column - 1
    return result


def match_staffs(reference: list[dict], predicted: list[dict]) -> dict:
    """Maximiza cardinalidade, depois minimiza distância; relação um-para-um."""
    eligible = [[_eligible(ref, pred) for pred in predicted] for ref in reference]
    ambiguous_refs = [
        ref["id"]
        for ref, row in zip(reference, eligible, strict=True)
        if sum(cost is not None for cost in row) > 1
    ]
    ambiguous_predictions = [
        column
        for column in range(len(predicted))
        if sum(row[column] is not None for row in eligible) > 1
    ]
    count = len(predicted)
    costs = [
        [cost if cost is not None else 1000.0 for cost in row]
        + [10.0 + i * 0.000001 for i in range(len(reference))]
        for row in eligible
    ]
    assignment = _assignment(costs)
    pairs = [
        {"reference_id": reference[row]["id"], "prediction_index": column}
        for row, column in enumerate(assignment)
        if column < count and eligible[row][column] is not None
    ]
    return {
        "pairs": pairs,
        "ambiguous_reference_ids": ambiguous_refs,
        "ambiguous_prediction_indices": ambiguous_predictions,
    }


def _rates(tp: int, fp: int, fn: int, *, allow_precision: bool = True) -> dict:
    precision = tp / (tp + fp) if allow_precision and tp + fp else NOT_EVALUABLE
    recall = tp / (tp + fn) if tp + fn else NOT_EVALUABLE
    if isinstance(precision, float) and isinstance(recall, float):
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
    else:
        f1 = NOT_EVALUABLE
    return {"precision": precision, "recall": recall, "f1": f1}


def _staff_metrics(reference: dict, predicted: dict, matching: dict) -> dict:
    refs = reference["staffs"]
    preds = predicted["staffs"]
    pairs = matching["pairs"]
    full = reference["coverage"]["staffs"] == "complete" and all(
        staff["review_state"] == "confirmed" for staff in refs
    )
    ref_by_id = {staff["id"]: staff for staff in refs}
    y_errors = []
    endpoint_errors = []
    edge_errors = []
    for pair in pairs:
        ref = ref_by_id[pair["reference_id"]]
        pred = preds[pair["prediction_index"]]
        edge_errors.extend(
            abs(ref["region"][key] - pred["region"][key])
            for key in ("left", "top", "right", "bottom")
        )
        if ref["lines"] is not None:
            for actual, found in zip(ref["lines"], pred["lines"], strict=True):
                y_errors.append(abs(actual["y"] - found["y"]))
                endpoint_errors.extend(
                    (
                        abs(actual["x_start"] - found["x_start"]),
                        abs(actual["x_end"] - found["x_end"]),
                    )
                )
    counts = (
        {"tp": len(pairs), "fp": len(preds) - len(pairs), "fn": len(refs) - len(pairs)}
        if full
        else {"tp": NOT_EVALUABLE, "fp": NOT_EVALUABLE, "fn": NOT_EVALUABLE}
    )
    rates = (
        _rates(**counts)
        if full
        else dict.fromkeys(("precision", "recall", "f1"), NOT_EVALUABLE)
    )
    return {
        "status": "evaluated" if full else NOT_EVALUABLE,
        "reference_count": len(refs),
        "confirmed_region_count": sum(s["review_state"] == "confirmed" for s in refs),
        "predicted_count": len(preds),
        "matched_count": len(pairs),
        **counts,
        **rates,
        "region_edge_mae_px": mean(edge_errors) if edge_errors else NOT_EVALUABLE,
        "region_edge_count": len(edge_errors),
        "line_y_mae_px": mean(y_errors) if y_errors else NOT_EVALUABLE,
        "line_y_count": len(y_errors),
        "line_endpoint_mae_px": mean(endpoint_errors)
        if endpoint_errors
        else NOT_EVALUABLE,
        "line_endpoint_count": len(endpoint_errors),
    }


def _system_metrics(reference: dict, predicted: dict, matching: dict) -> dict:
    known = [s for s in reference["systems"] if s["review_state"] == "confirmed"]
    groups = predicted["systems"]["groups"]
    result = {
        "reference_system_count": len(reference["systems"]),
        "confirmed_system_count": len(known),
        "predicted_system_count": len(groups),
        "prediction_status": predicted["systems"]["status"],
    }
    if (
        not known
        or predicted["systems"]["status"] != "grouped"
        or matching["ambiguous_reference_ids"]
        or matching["ambiguous_prediction_indices"]
    ):
        return {
            **result,
            "status": NOT_EVALUABLE,
            "correct_systems": NOT_EVALUABLE,
            "split_systems": NOT_EVALUABLE,
            "merged_systems": NOT_EVALUABLE,
            "misassigned_staffs": NOT_EVALUABLE,
            "ambiguous_predicted_groups": NOT_EVALUABLE,
            "pair_tp": NOT_EVALUABLE,
            "pair_fp": NOT_EVALUABLE,
            "pair_fn": NOT_EVALUABLE,
            "pair_precision": NOT_EVALUABLE,
            "pair_recall": NOT_EVALUABLE,
            "pair_f1": NOT_EVALUABLE,
        }
    ref_to_pred = {p["reference_id"]: p["prediction_index"] for p in matching["pairs"]}
    pred_to_group = {
        index: group_id for group_id, group in enumerate(groups) for index in group
    }
    staff_to_system = {staff_id: s["id"] for s in known for staff_id in s["staff_ids"]}
    matched = {
        staff_id: pred_to_group[pred_index]
        for staff_id, pred_index in ref_to_pred.items()
        if staff_id in staff_to_system and pred_index in pred_to_group
    }
    pair_tp = pair_fp = pair_fn = 0
    for first, second in combinations(matched, 2):
        actual_same = staff_to_system[first] == staff_to_system[second]
        predicted_same = matched[first] == matched[second]
        if actual_same and predicted_same:
            pair_tp += 1
        elif actual_same:
            pair_fn += 1
        elif predicted_same:
            pair_fp += 1
    split = sum(
        len({matched[staff_id] for staff_id in s["staff_ids"] if staff_id in matched})
        > 1
        for s in known
    )
    merged = sum(
        len(
            {
                staff_to_system[staff_id]
                for staff_id in matched
                if matched[staff_id] == index
            }
        )
        > 1
        for index in range(len(groups))
    )
    misassigned = ambiguous_groups = 0
    for group_index in range(len(groups)):
        labels = [
            staff_to_system[staff_id]
            for staff_id in matched
            if matched[staff_id] == group_index
        ]
        if not labels:
            continue
        frequencies = {label: labels.count(label) for label in set(labels)}
        best = max(frequencies.values())
        if sum(value == best for value in frequencies.values()) > 1:
            ambiguous_groups += 1
        else:
            misassigned += len(labels) - best
    full = (
        reference["coverage"]["systems"] == "complete"
        and reference["coverage"]["staffs"] == "complete"
        and all(not s["partial_visible"] for s in known)
    )
    correct = 0
    if full:
        for system in known:
            members = system["staff_ids"]
            if any(staff_id not in ref_to_pred for staff_id in members):
                continue
            mapped = {ref_to_pred[staff_id] for staff_id in members}
            if any(mapped == set(group) for group in groups):
                correct += 1
    rates = _rates(pair_tp, pair_fp, pair_fn)
    return {
        **result,
        "status": "evaluated" if full else "partial_evaluation",
        "correct_systems": correct if full else NOT_EVALUABLE,
        "split_systems": split,
        "merged_systems": merged,
        "misassigned_staffs": misassigned,
        "ambiguous_predicted_groups": ambiguous_groups,
        "pair_tp": pair_tp,
        "pair_fp": pair_fp,
        "pair_fn": pair_fn,
        "pair_precision": rates["precision"],
        "pair_recall": rates["recall"],
        "pair_f1": rates["f1"],
    }


def _clef_metrics(reference: dict, predicted: dict, matching: dict) -> dict:
    by_staff = {item["staff_id"]: item for item in reference["clefs"]}
    refs = {s["id"]: s for s in reference["staffs"]}
    ref_to_pred = {p["reference_id"]: p["prediction_index"] for p in matching["pairs"]}
    tp = fp = fn = tn = inconclusive = wrong_location = negative_fp = 0
    positive = negative = unknown = unscored = 0
    box_errors = []
    for staff_id, staff in refs.items():
        item = by_staff.get(staff_id)
        if (
            staff["review_state"] != "confirmed"
            or item is None
            or item["state"] == "unknown"
        ):
            unknown += 1
            pred_index = ref_to_pred.get(staff_id)
            if (
                pred_index is not None
                and predicted["clefs"][pred_index]["status"] == "detected"
            ):
                unscored += 1
            continue
        is_positive = item["state"] == "present" and item["kind"] == "treble"
        positive += is_positive
        negative += not is_positive
        pred_index = ref_to_pred.get(staff_id)
        if pred_index is None:
            if is_positive:
                fn += 1
            continue
        observation = predicted["clefs"][pred_index]
        if observation["status"] == "inconclusive":
            inconclusive += 1
            if is_positive:
                fn += 1
            continue
        if observation["status"] != "detected":
            if is_positive:
                fn += 1
            else:
                tn += 1
            continue
        if not is_positive:
            fp += 1
            negative_fp += 1
            continue
        if (
            item["region"] is not None
            and _iou(item["region"], observation["region"]) < 0.3
        ):
            wrong_location += 1
            fp += 1
            fn += 1
            continue
        tp += 1
        if item["region"] is not None:
            box_errors.extend(
                abs(item["region"][key] - observation["region"][key])
                for key in ("left", "top", "right", "bottom")
            )
    matched_indices = set(ref_to_pred.values())
    for index, observation in enumerate(predicted["clefs"]):
        if index in matched_indices or observation["status"] != "detected":
            continue
        if (
            reference["coverage"]["staffs"] == "complete"
            and reference["coverage"]["clefs"] == "complete"
        ):
            fp += 1
        else:
            unscored += 1
    rates = _rates(tp, fp, fn, allow_precision=negative > 0)
    return {
        "status": "evaluated" if positive or negative else NOT_EVALUABLE,
        "known_positive": positive,
        "known_negative": negative,
        "unknown": unknown,
        "unscored_detections": unscored,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "inconclusive": inconclusive,
        "wrong_location": wrong_location,
        "false_positives_on_known_negatives": negative_fp,
        **rates,
        "negative_false_positive_rate": negative_fp / negative
        if negative
        else NOT_EVALUABLE,
        "region_edge_mae_px": mean(box_errors) if box_errors else NOT_EVALUABLE,
        "region_edge_count": len(box_errors),
    }


def evaluate_page(reference: dict, prediction: dict) -> dict:
    """Avalia uma página validada; funções internas não executam detectores."""
    confirmed = [s for s in reference["staffs"] if s["review_state"] == "confirmed"]
    matching = match_staffs(confirmed, prediction["staffs"])
    return {
        "image_id": reference["image"]["id"],
        "split": reference["split"],
        "staffs": _staff_metrics(reference, prediction, matching),
        "systems": _system_metrics(reference, prediction, matching),
        "clefs": _clef_metrics(reference, prediction, matching),
        "matching": matching,
    }


def aggregate_reports(reports: list[dict]) -> dict:
    """Agrega somente denominadores avaliáveis; não interpreta ausência como 100%."""
    staff_pages = [r["staffs"] for r in reports if r["staffs"]["status"] == "evaluated"]
    system_pages = [
        r["systems"] for r in reports if r["systems"]["status"] == "evaluated"
    ]
    clef_pages = [r["clefs"] for r in reports if r["clefs"]["status"] == "evaluated"]

    def weighted(section: str, average: str, count: str):
        values = [r[section] for r in reports if r[section][count] > 0]
        denominator = sum(item[count] for item in values)
        return (
            sum(item[average] * item[count] for item in values) / denominator
            if denominator
            else NOT_EVALUABLE
        )

    staff_counts = {
        key: sum(page[key] for page in staff_pages) for key in ("tp", "fp", "fn")
    }
    pair_counts = {
        key: sum(page[key] for page in system_pages)
        for key in ("pair_tp", "pair_fp", "pair_fn")
    }
    clef_counts = {
        key: sum(page[key] for page in clef_pages)
        for key in ("tp", "fp", "fn", "tn", "inconclusive")
    }
    known_positive = sum(page["known_positive"] for page in clef_pages)
    known_negative = sum(page["known_negative"] for page in clef_pages)
    negative_fp = sum(page["false_positives_on_known_negatives"] for page in clef_pages)
    staff_rates = (
        _rates(**staff_counts)
        if staff_pages
        else dict.fromkeys(("precision", "recall", "f1"), NOT_EVALUABLE)
    )
    pair_rates = (
        _rates(pair_counts["pair_tp"], pair_counts["pair_fp"], pair_counts["pair_fn"])
        if system_pages
        else dict.fromkeys(("precision", "recall", "f1"), NOT_EVALUABLE)
    )
    clef_rates = (
        _rates(
            clef_counts["tp"],
            clef_counts["fp"],
            clef_counts["fn"],
            allow_precision=known_negative > 0,
        )
        if clef_pages
        else dict.fromkeys(("precision", "recall", "f1"), NOT_EVALUABLE)
    )
    return {
        "image_count": len(reports),
        "staffs": {
            "status": "evaluated" if staff_pages else NOT_EVALUABLE,
            "evaluated_images": len(staff_pages),
            "annotated_count": sum(page["reference_count"] for page in staff_pages),
            "predicted_count": sum(page["predicted_count"] for page in staff_pages),
            **staff_counts,
            **staff_rates,
            "region_edge_mae_px": weighted(
                "staffs", "region_edge_mae_px", "region_edge_count"
            ),
            "region_edge_count": sum(r["staffs"]["region_edge_count"] for r in reports),
            "line_y_mae_px": weighted("staffs", "line_y_mae_px", "line_y_count"),
            "line_y_count": sum(r["staffs"]["line_y_count"] for r in reports),
            "line_endpoint_mae_px": weighted(
                "staffs", "line_endpoint_mae_px", "line_endpoint_count"
            ),
            "line_endpoint_count": sum(
                r["staffs"]["line_endpoint_count"] for r in reports
            ),
        },
        "systems": {
            "status": "evaluated" if system_pages else NOT_EVALUABLE,
            "evaluated_images": len(system_pages),
            "partial_evaluation_images": sum(
                r["systems"]["status"] == "partial_evaluation" for r in reports
            ),
            "confirmed_system_count": sum(
                page["confirmed_system_count"] for page in system_pages
            ),
            "predicted_system_count": sum(
                page["predicted_system_count"] for page in system_pages
            ),
            "correct_systems": (
                sum(page["correct_systems"] for page in system_pages)
                if system_pages
                else NOT_EVALUABLE
            ),
            **pair_counts,
            "pair_precision": pair_rates["precision"],
            "pair_recall": pair_rates["recall"],
            "pair_f1": pair_rates["f1"],
        },
        "clefs": {
            "status": "evaluated" if clef_pages else NOT_EVALUABLE,
            "evaluated_images": len(clef_pages),
            "known_positive": known_positive,
            "known_negative": known_negative,
            "false_positives_on_known_negatives": negative_fp,
            "negative_false_positive_rate": (
                negative_fp / known_negative if known_negative else NOT_EVALUABLE
            ),
            **clef_counts,
            **clef_rates,
            "region_edge_mae_px": weighted(
                "clefs", "region_edge_mae_px", "region_edge_count"
            ),
            "region_edge_count": sum(r["clefs"]["region_edge_count"] for r in reports),
        },
    }
