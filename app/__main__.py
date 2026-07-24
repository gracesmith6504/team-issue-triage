import argparse
import logging

from app.config import load_config
from app.triage import run_digest, run_triage


def main():
    parser = argparse.ArgumentParser(description="Team Issue Triage Agent")
    parser.add_argument(
        "--mode",
        choices=["triage", "digest"],
        default="triage",
        help="Run mode: triage (assess new issues) or digest (flush daily digest)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    config = load_config()

    if args.mode == "triage":
        run_triage(config)
    elif args.mode == "digest":
        run_digest(config)


if __name__ == "__main__":
    main()
