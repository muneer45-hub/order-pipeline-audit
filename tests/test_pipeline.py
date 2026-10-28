"""Pipeline behaviour: happy path, reruns, empty/malformed input, duplicates, nulls,
schema change, late-arriving data, invalid references, partial failure and retry."""
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline import runner
from pipeline.cli import main
from pipeline.runner import run_pipeline

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "data" / "sample"
KEY_FILE = ROOT / "data" / "sample_expected" / "expected_rejects.csv"
NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)

HEADERS = {
    "customers": "customer_id,full_name,email,country,updated_at",
    "products": "product_id,product_name,category,list_price,updated_at",
    "orders": "order_id,customer_id,product_id,quantity,unit_price,order_status,order_ts,updated_at",
}
ORDER_OK = "O00000001,C000001,P00001,2,10.50,placed,2026-02-01T00:00:00Z,2026-02-01T00:00:00Z"
GOOD = {
    "customers": ["C000001,Asha Sharma,asha@example.com,IN,2026-01-01T00:00:00Z"],
    "products": ["P00001,Product 1,books,10.50,2026-01-01T00:00:00Z"],
    "orders": [ORDER_OK],
}


def write_batch(folder, **rows_by_entity):
    folder.mkdir(parents=True, exist_ok=True)
    for entity, header in HEADERS.items():
        rows = rows_by_entity.get(entity, GOOD[entity])
        (folder / f"{entity}.csv").write_text(
            header + "\n" + "".join(r + "\n" for r in rows), encoding="utf-8")


def q(db, sql, *args):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def count(db, table):
    return q(db, f"SELECT COUNT(*) FROM {table}")[0][0]


def statuses(summary):
    return {f["source_file"]: f["file_status"] for f in summary["files"]}


def test_happy_path(tmp_path):
    db = tmp_path / "t.db"
    write_batch(tmp_path / "in")
    s = run_pipeline(tmp_path / "in", db, now=NOW)
    assert s["status"] == "success"
    assert (s["rows_read"], s["rows_loaded"], s["rows_rejected"]) == (3, 3, 0)
    assert q(db, "SELECT line_total_cents FROM fact_orders") == [(2100,)]
    assert q(db, "SELECT status FROM pipeline_runs") == [("success",)]


def test_rerun_of_same_input_creates_no_duplicates(tmp_path):
    db = tmp_path / "t.db"
    write_batch(tmp_path / "in")
    run_pipeline(tmp_path / "in", db, now=NOW)
    second = run_pipeline(tmp_path / "in", db, now=NOW)
    assert set(statuses(second).values()) == {"skipped_already_processed"}
    assert second["rows_loaded"] == 0
    assert (count(db, "dim_customers"), count(db, "dim_products"),
            count(db, "fact_orders")) == (1, 1, 1)
    assert count(db, "pipeline_runs") == 2


def test_empty_batch_with_only_headers_succeeds(tmp_path):
    db = tmp_path / "t.db"
    write_batch(tmp_path / "in", customers=[], products=[], orders=[])
    s = run_pipeline(tmp_path / "in", db, now=NOW)
    assert s["status"] == "success"
    assert s["rows_read"] == 0 and count(db, "fact_orders") == 0


def test_completely_empty_file_fails_that_file_only(tmp_path):
    db = tmp_path / "t.db"
    write_batch(tmp_path / "in")
    (tmp_path / "in" / "customers.csv").write_text("")
    s = run_pipeline(tmp_path / "in", db, now=NOW)
    assert s["status"] == "failed"
    st = statuses(s)
    assert st["customers.csv"] == "failed"
    assert st["products.csv"] == "loaded"
    assert st["orders.csv"] == "failed"  # depends on customers
    assert count(db, "run_errors") == 2


def test_unexpected_schema_change_is_rejected(tmp_path):
    db = tmp_path / "t.db"
    write_batch(tmp_path / "in")
    (tmp_path / "in" / "customers.csv").write_text(
        "customer_id,full_name,email,country,updated_at,phone\n"
        "C000001,Asha,a@example.com,IN,2026-01-01T00:00:00Z,123\n")
    s = run_pipeline(tmp_path / "in", db, now=NOW)
    assert s["status"] == "failed"
    assert "unexpected header" in s["failure_reason"]
    assert count(db, "dim_customers") == 0


def test_customer_null_and_malformed_rows_are_quarantined(tmp_path):
    db = tmp_path / "t.db"
    write_batch(tmp_path / "in", customers=GOOD["customers"] + [
        "C000002,,x@example.com,IN,2026-01-01T00:00:00Z",   # missing name
        "C000003,Only Two"])                                  # too few columns
    s = run_pipeline(tmp_path / "in", db, now=NOW)
    assert s["status"] == "success"
    assert count(db, "dim_customers") == 1
    assert q(db, "SELECT source_row_number, reject_reason FROM rejected_records "
                 "ORDER BY source_row_number") == [(2, "missing_required_field"),
                                                   (3, "malformed_row")]


@pytest.mark.parametrize("bad_row, reason", [
    ("O00000002,C999999,P00001,1,5.00,placed,2026-02-01T00:00:00Z,2026-02-01T00:00:00Z",
     "invalid_customer_ref"),
    ("O00000002,C000001,P99999,1,5.00,placed,2026-02-01T00:00:00Z,2026-02-01T00:00:00Z",
     "invalid_product_ref"),
    ("O00000002,C000001,P00001,0,5.00,placed,2026-02-01T00:00:00Z,2026-02-01T00:00:00Z",
     "invalid_quantity"),
    ("O00000002,C000001,P00001,1,-1.00,placed,2026-02-01T00:00:00Z,2026-02-01T00:00:00Z",
     "invalid_price"),
    ("O00000002,C000001,P00001,1,5.00,placed,2099-01-01T00:00:00Z,2099-01-01T00:00:00Z",
     "future_order_ts"),
    ("O00000002,C000001,P00001,1,5.00,placed,2026-02-01T00:00:00Z",
     "malformed_row"),
    ("O00000002,,P00001,1,5.00,placed,2026-02-01T00:00:00Z,2026-02-01T00:00:00Z",
     "missing_required_field"),
])
def test_bad_order_rows_are_rejected_with_reason(tmp_path, bad_row, reason):
    db = tmp_path / "t.db"
    write_batch(tmp_path / "in", orders=[ORDER_OK, bad_row])
    s = run_pipeline(tmp_path / "in", db, now=NOW)
    assert (s["rows_loaded"], s["rows_rejected"]) == (3, 1)
    assert q(db, "SELECT source_file, source_row_number, reject_reason FROM rejected_records"
             ) == [("orders.csv", 2, reason)]
    assert "O00000002" not in [r[0] for r in q(db, "SELECT order_id FROM fact_orders")]


def test_duplicate_keys_keep_latest_even_when_out_of_order(tmp_path):
    db = tmp_path / "t.db"
    write_batch(tmp_path / "in", customers=[
        "C000001,Asha New,asha@example.com,IN,2026-03-01T00:00:00Z",   # newer, first
        "C000001,Asha Old,asha@example.com,IN,2026-01-01T00:00:00Z"])  # older, second
    run_pipeline(tmp_path / "in", db, now=NOW)
    assert q(db, "SELECT full_name FROM dim_customers") == [("Asha New",)]
    assert q(db, "SELECT source_row_number, reject_reason FROM rejected_records") == [
        (2, "duplicate_key")]


def test_late_arriving_data_never_overwrites_and_history_is_kept(tmp_path):
    db = tmp_path / "t.db"
    write_batch(tmp_path / "day1")
    run_pipeline(tmp_path / "day1", db, now=NOW)

    # day 2: an OLDER version of the customer arrives late
    write_batch(tmp_path / "day2", customers=[
        "C000001,Old Name,old@example.com,IN,2025-12-01T00:00:00Z"])
    late = run_pipeline(tmp_path / "day2", db, now=NOW)
    assert late["rows_rejected"] == 1
    assert q(db, "SELECT reject_reason FROM rejected_records") == [("stale_update",)]
    assert q(db, "SELECT full_name FROM dim_customers") == [("Asha Sharma",)]

    # day 3: NEWER versions arrive and are applied; order status change is kept as history
    write_batch(tmp_path / "day3",
                customers=["C000001,Asha Updated,asha@example.com,IN,2026-06-01T00:00:00Z"],
                orders=["O00000001,C000001,P00001,2,10.50,shipped,"
                        "2026-02-01T00:00:00Z,2026-03-01T00:00:00Z"])
    run_pipeline(tmp_path / "day3", db, now=NOW)
    assert q(db, "SELECT full_name FROM dim_customers") == [("Asha Updated",)]
    assert q(db, "SELECT order_status FROM fact_orders") == [("shipped",)]
    assert q(db, "SELECT order_status FROM order_status_history ORDER BY event_ts") == [
        ("placed",), ("shipped",)]


def test_partial_failure_rolls_back_then_retry_succeeds(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    write_batch(tmp_path / "in")
    real_loader = runner.LOADERS["orders"]

    def crash_after_writing(conn, run_id, source_file, accepted):
        real_loader(conn, run_id, source_file, accepted)   # rows written inside the transaction
        raise RuntimeError("simulated crash after writing")

    monkeypatch.setitem(runner.LOADERS, "orders", crash_after_writing)
    first = run_pipeline(tmp_path / "in", db, now=NOW)
    assert first["status"] == "failed"
    assert statuses(first)["orders.csv"] == "failed"
    assert count(db, "dim_customers") == 1          # earlier files stay committed
    assert count(db, "fact_orders") == 0            # the failed file was rolled back
    assert count(db, "order_status_history") == 0
    assert q(db, "SELECT stage FROM run_errors") == [("processing",)]

    monkeypatch.undo()                              # the "outage" is over: retry = rerun
    second = run_pipeline(tmp_path / "in", db, now=NOW)
    assert second["status"] == "success"
    assert statuses(second) == {"customers.csv": "skipped_already_processed",
                                "products.csv": "skipped_already_processed",
                                "orders.csv": "loaded"}
    assert count(db, "fact_orders") == 1


def load_expected():
    with open(KEY_FILE, newline="", encoding="utf-8") as f:
        return {(r["source_file"], int(r["source_row_number"]), r["expected_reason"])
                for r in csv.DictReader(f)}


def test_sample_end_to_end_matches_answer_key_and_reconciles(tmp_path):
    db = tmp_path / "sample.db"
    first = run_pipeline(SAMPLE_DIR, db, now=NOW)
    assert first["status"] == "success"

    actual = set(q(db, "SELECT source_file, source_row_number, reject_reason "
                       "FROM rejected_records"))
    assert actual == load_expected()

    for name, rows, loaded, rejected in q(
            db, "SELECT source_file, row_count, rows_loaded, rows_rejected FROM run_input_files"):
        assert rows == loaded + rejected, name      # source-to-target reconciliation

    orphans_c = "SELECT COUNT(*) FROM fact_orders WHERE customer_id NOT IN " \
                "(SELECT customer_id FROM dim_customers)"
    orphans_p = "SELECT COUNT(*) FROM fact_orders WHERE product_id NOT IN " \
                "(SELECT product_id FROM dim_products)"
    assert q(db, orphans_c)[0][0] == 0 and q(db, orphans_p)[0][0] == 0

    tables = ("dim_customers", "dim_products", "fact_orders")
    before = {t: count(db, t) for t in tables}
    second = run_pipeline(SAMPLE_DIR, db, now=NOW)
    assert set(statuses(second).values()) == {"skipped_already_processed"}
    assert {t: count(db, t) for t in tables} == before


def test_cli_run_returns_zero_on_success(tmp_path):
    write_batch(tmp_path / "in")
    assert main(["run", "--input-dir", str(tmp_path / "in"),
                 "--db", str(tmp_path / "cli.db")]) == 0