import argparse
import logging
import os
from pathlib import Path

from app.triage import (
    check_closed_issues,
    run_digest,
    run_refresh,
    run_report,
    run_review,
    run_triage,
)
from app.config import load_config


def _bootstrap_gcp_credentials() -> None:
    """Write GCP SA key from env var JSON to a temp file.

    When running inside an OpenShell sandbox we can't mount volume secrets,
    so GOOGLE_APPLICATION_CREDENTIALS_JSON carries the key content as a string.
    This writes it to /tmp/gcp-key.json before the Vertex client initialises.
    No-op if GOOGLE_APPLICATION_CREDENTIALS already points to a file.
    """
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    json_content = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not json_content:
        return
    key_path = "/tmp/gcp-key.json"
    with open(key_path, "w") as f:
        f.write(json_content)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path


def main():
    parser = argparse.ArgumentParser(description="Team issue triage agent")
    parser.add_argument(
        "--mode",
        choices=[
            "triage",
            "digest",
            "review",
            "report",
            "serve",
            "refresh",
            "check-closed",
            "worker-triage",
            "worker-report",
        ],
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

    _bootstrap_gcp_credentials()
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
    elif args.mode == "refresh":
        run_refresh(config)
    elif args.mode == "check-closed":
        check_closed_issues(config)
    elif args.mode == "worker-triage":
        from app.worker import worker_triage

        worker_triage(config)
    elif args.mode == "worker-report":
        from app.worker import worker_report

        worker_report(config)
    else:
        run_triage(config)


if __name__ == "__main__":
    main()
