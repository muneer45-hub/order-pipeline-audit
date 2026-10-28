"""Command line entry point.

    python -m pipeline.cli run    --input-dir data/sample --db output/pipeline.db
    python -m pipeline.cli report --db output/pipeline.db [--out reports/audit_report.md]
    python -m pipeline.cli trace  --db output/pipeline.db --order-id O00000001
"""
import argparse
import sys
from pathlib import Path

from .config import DEFAULT_DB_PATH, DEFAULT_INPUT_DIR
from .report import build_report, format_trace, trace_order
from .runner import run_pipeline
from .schema import connect


def build_parser():
    parser = argparse.ArgumentParser(prog="order-pipeline",
                                     description="Order pipeline with audit trail")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="process the input files once")
    run.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    run.add_argument("--db", default=str(DEFAULT_DB_PATH))

    report = sub.add_parser("report", help="print the audit report and run all checks")
    report.add_argument("--db", default=str(DEFAULT_DB_PATH))
    report.add_argument("--out", help="also write the report to this markdown file")

    trace = sub.add_parser("trace", help="trace one order back to its source file and row")
    trace.add_argument("--db", default=str(DEFAULT_DB_PATH))
    trace.add_argument("--order-id", required=True)
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


def _open_existing(db):
    if not Path(db).exists():
        print(f"error: database not found: {db} (run the pipeline first)", file=sys.stderr)
        return None
    return connect(db)


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.command == "run":
        summary = run_pipeline(args.input_dir, args.db)
        print_summary(summary)
        return 0 if summary["status"] == "success" else 1

    conn = _open_existing(args.db)
    if conn is None:
        return 2
    try:
        if args.command == "report":
            text, all_passed = build_report(conn)
            print(text)
            if args.out:
                out = Path(args.out)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(text, encoding="utf-8")
                print(f"Report written to {out}")
            return 0 if all_passed else 1
        if args.command == "trace":
            trace = trace_order(conn, args.order_id)
            if trace is None:
                print(f"Order {args.order_id} is not loaded.")
                return 1
            print(format_trace(trace))
            return 0
    finally:
        conn.close()
    return 2


if __name__ == "__main__":
    sys.exit(main())