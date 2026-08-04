import argparse
import logging
from pathlib import Path

from app.config import load_config
from app.triage import run_digest, run_report, run_review, run_triage


def main():
    parser = argparse.ArgumentParser(description="Team issue triage agent")
    parser.add_argument(
        "--mode",
        choices=["triage", "digest", "review", "report", "serve"],
        default="triage",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--since", type=int, default=None)
    parser.add_argument("--team", type=str, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--format",
        choices=["markdown", "html"],
        default=None,
        dest="report_format",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    config = load_config()

    if args.mode == "review":
        run_review(config, since_hours=args.since, team_filter=args.team)
    elif args.mode == "digest":
        run_digest(config)
    elif args.mode == "report":
        run_report(config, output_path=args.output, fmt=args.report_format)
    elif args.mode == "serve":
        from app.server import start_server

        start_server(config)
    else:
        run_triage(config)


if __name__ == "__main__":
    main()
