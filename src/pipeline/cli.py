"""Command line entry point:  python -m pipeline.cli run --input-dir data/sample"""
import argparse
import sys

from .config import DEFAULT_DB_PATH, DEFAULT_INPUT_DIR
from .runner import run_pipeline


def build_parser():
    parser = argparse.ArgumentParser(prog="order-pipeline",
                                     description="Order pipeline with audit trail")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="process the input files once")
    run.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    run.add_argument("--db", default=str(DEFAULT_DB_PATH))
    return parser


def print_summary(summary):
    print(f"Run {summary['run_id']}: {summary['status'].upper()}")
    for f in summary["files"]:
        print(f"  {f['source_file']:<14} {f['file_status']:<27} "
              f"read={f['row_count']:<7} loaded={f['rows_loaded']:<7} "
              f"rejected={f['rows_rejected']}")
    print(f"  TOTAL read={summary['rows_read']} loaded={summary['rows_loaded']} "
          f"rejected={summary['rows_rejected']}")
    if summary["failure_reason"]:
        print(f"  FAILURE: {summary['failure_reason']}")


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "run":
        summary = run_pipeline(args.input_dir, args.db)
        print_summary(summary)
        return 0 if summary["status"] == "success" else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())