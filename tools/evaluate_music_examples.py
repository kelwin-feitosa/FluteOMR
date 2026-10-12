"""Compara transcrições com referências próprias somente após a inferência."""

import argparse
import json
from pathlib import Path

from fluteomr.image_io import load_image
from fluteomr.transcription import transcribe_one_measure


def evaluate(corpus_dir: Path, left: int, right: int) -> list[dict]:
    rows = []
    for image_path in sorted(corpus_dir.glob("*.png")):
        score = transcribe_one_measure(
            load_image(image_path), measure_left=left, measure_right=right
        )
        predicted = score.parts[0].measures[0].notes
        # A referência é aberta somente depois de concluir a inferência.
        reference = json.loads(
            image_path.with_suffix(".reference.json").read_text(encoding="utf-8")
        )
        expected = reference["notes"]
        tolerance = 0.75 * reference["staff_spacing"]
        pairs = [
            (
                abs(
                    (note.source_region.left + note.source_region.right) / 2
                    - truth["center_x"]
                ),
                predicted_index,
                expected_index,
            )
            for predicted_index, note in enumerate(predicted)
            for expected_index, truth in enumerate(expected)
        ]
        pairs.sort()
        matched_predicted = set()
        matched_expected = set()
        pitch_correct = duration_correct = 0
        for distance, predicted_index, expected_index in pairs:
            if distance > tolerance:
                break
            if (
                predicted_index in matched_predicted
                or expected_index in matched_expected
            ):
                continue
            matched_predicted.add(predicted_index)
            matched_expected.add(expected_index)
            note, truth = predicted[predicted_index], expected[expected_index]
            pitch_correct += note.pitch is not None and (
                note.pitch.step,
                note.pitch.octave,
            ) == (truth["step"], truth["octave"])
            duration_correct += (
                note.duration is not None and note.duration.kind == truth["duration"]
            )
        rows.append(
            {
                "image": image_path.name,
                "split": reference["split"],
                "heads_expected": len(expected),
                "heads_detected": len(predicted),
                "matched": len(matched_predicted),
                "false_positives": len(predicted) - len(matched_predicted),
                "missed": len(expected) - len(matched_expected),
                "pitch_correct": pitch_correct,
                "duration_correct": duration_correct,
                "measure_complete": not score.issues(),
                "issues": score.issues(),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliar corpus musical sintético")
    parser.add_argument(
        "--corpus-dir", type=Path, default=Path("outputs/sprint-1a/corpus")
    )
    parser.add_argument("--measure-left", type=int, default=110)
    parser.add_argument("--measure-right", type=int, default=410)
    args = parser.parse_args()
    rows = evaluate(args.corpus_dir, args.measure_left, args.measure_right)
    if not rows:
        parser.error("nenhuma imagem PNG encontrada")
    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
