"""The audit report: checks pass on clean data, detect corruption, and trace works."""
from datetime import datetime, timezone
from pathlib import Path

from pipeline.cli import main
from pipeline.config import ENTITIES
from pipeline.ingest import file_checksum, read_csv
from pipeline.report import run_checks, trace_order
from pipeline.runner import run_pipeline
from pipeline.schema import connect

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"
NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)


def loaded_db(tmp_path):
    db = tmp_path / "s.db"
    run_pipeline(SAMPLE_DIR, db, now=NOW)
    return db


def test_all_checks_pass_on_sample(tmp_path):
    conn = connect(loaded_db(tmp_path))
    try:
        results = run_checks(conn)
    finally:
        conn.close()
    assert all(ok for _, ok, _ in results), results


def test_checks_detect_corrupted_data(tmp_path):
    conn = connect(loaded_db(tmp_path))
    try:
        conn.execute("UPDATE fact_orders SET line_total_cents = line_total_cents + 1 "
                     "WHERE order_id = (SELECT MIN(order_id) FROM fact_orders)")
        conn.execute("UPDATE run_input_files SET rows_loaded = rows_loaded + 1 "
                     "WHERE source_file = 'orders.csv'")
        conn.commit()
        failed = {name for name, ok, _ in run_checks(conn) if not ok}
    finally:
        conn.close()
    assert "line_total_is_quantity_times_price" in failed
    assert "source_to_target_counts" in failed


def test_trace_links_output_row_to_its_source_row(tmp_path):
    conn = connect(loaded_db(tmp_path))
    try:
        order_id = conn.execute("SELECT MIN(order_id) FROM fact_orders").fetchone()[0]
        trace = trace_order(conn, order_id)
    finally:
        conn.close()
    order = trace["order"]
    assert order["source_file"] == "orders.csv"
    # the recorded row number really points at this order in the input file
    source_rows = dict(read_csv(SAMPLE_DIR / "orders.csv", ENTITIES["orders"]["columns"]))
    assert source_rows[order["source_row_number"]][0] == order_id
    assert order["file_checksum"] == file_checksum(SAMPLE_DIR / "orders.csv")
    assert len(trace["history"]) >= 1


def test_trace_of_unknown_order_returns_none(tmp_path):
    conn = connect(loaded_db(tmp_path))
    try:
        assert trace_order(conn, "O99999999") is None
    finally:
        conn.close()


def test_report_command_writes_file_and_passes(tmp_path):
    db = loaded_db(tmp_path)
    out = tmp_path / "reports" / "audit_report.md"
    assert main(["report", "--db", str(db), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Reject breakdown" in text and "ALL CHECKS PASSED" in text


def test_report_command_fails_cleanly_when_database_is_missing(tmp_path):
    assert main(["report", "--db", str(tmp_path / "missing.db")]) == 2