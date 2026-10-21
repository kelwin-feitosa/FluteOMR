"""CLI de preparação, checagem e confirmação de referência musical humana."""

import argparse
import json
from pathlib import Path

from fluteomr.music_review import confirm_review, prepare_review, verify_review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("source", type=Path)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--id", required=True)
    prepare.add_argument("--work-id")
    prepare.add_argument(
        "--crop",
        type=int,
        nargs=4,
        required=True,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
    )
    prepare.add_argument("--scale", type=int, default=1)
    prepare.add_argument("--candidate", type=Path)
    prepare.add_argument("--measures", nargs="+", type=int, required=True)
    prepare.add_argument("--staff-id")
    prepare.add_argument("--system-id")
    prepare.add_argument("--measure-left", type=int, required=True)
    prepare.add_argument("--measure-right", type=int, required=True)
    prepare.add_argument("--auto-bars", action="store_true")
    for action in ("check", "confirm"):
        command = sub.add_parser(action)
        command.add_argument("manifest", type=Path)
        if action == "confirm":
            command.add_argument("--reviewer", required=True)
            command.add_argument("--confirm-reviewed", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            result = prepare_review(
                args.source,
                args.output_dir,
                example_id=args.id,
                crop=tuple(args.crop),
                scale=args.scale,
                reference=args.candidate,
                measures=tuple(args.measures),
                staff_id=args.staff_id,
                system_id=args.system_id,
                configured={
                    "clef": "treble",
                    "time": "4/4",
                    "measure_left": args.measure_left,
                    "measure_right": args.measure_right,
                    "auto_bars": args.auto_bars,
                },
                work_id=args.work_id,
            )
            print(result)
        else:
            if args.action == "confirm":
                confirm_review(
                    args.manifest,
                    reviewer=args.reviewer,
                    confirm_reviewed=args.confirm_reviewed,
                )
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            print(
                json.dumps(
                    [verify_review(args.manifest, row) for row in manifest["examples"]],
                    indent=2,
                    ensure_ascii=False,
                )
            )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
