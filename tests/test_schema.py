import sqlite3

from pipeline.schema import init_db

EXPECTED_TABLES = {
    "pipeline_runs", "run_input_files", "processed_files", "rejected_records",
    "run_errors", "dim_customers", "dim_products", "fact_orders", "order_status_history",
}


def test_init_db_creates_all_tables():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert EXPECTED_TABLES <= names


def test_init_db_is_idempotent():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    init_db(conn)  # second call must not fail