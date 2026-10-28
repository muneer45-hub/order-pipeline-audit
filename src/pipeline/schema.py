"""SQLite schema: curated tables and audit tables.

Money is stored as integer cents so sums reconcile exactly (no float rounding).
Every curated row carries run_id, source_file and source_row_number (lineage).
"""
import sqlite3
from pathlib import Path

DDL = """
-- ---------- audit tables ----------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    input_dir       TEXT NOT NULL,
    rows_read       INTEGER NOT NULL DEFAULT 0,
    rows_loaded     INTEGER NOT NULL DEFAULT 0,
    rows_rejected   INTEGER NOT NULL DEFAULT 0,
    failure_reason  TEXT
);

CREATE TABLE IF NOT EXISTS run_input_files (
    run_id          TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source_file     TEXT NOT NULL,
    entity          TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    file_checksum   TEXT NOT NULL,
    row_count       INTEGER NOT NULL DEFAULT 0,
    rows_loaded     INTEGER NOT NULL DEFAULT 0,
    rows_rejected   INTEGER NOT NULL DEFAULT 0,
    file_status     TEXT NOT NULL
                    CHECK (file_status IN ('loaded', 'skipped_already_processed', 'failed')),
    failure_reason  TEXT,
    PRIMARY KEY (run_id, source_file)
);

CREATE TABLE IF NOT EXISTS processed_files (
    file_checksum   TEXT PRIMARY KEY,
    source_file     TEXT NOT NULL,
    run_id          TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    processed_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rejected_records (
    reject_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source_file         TEXT NOT NULL,
    source_row_number   INTEGER NOT NULL,
    record_key          TEXT,
    reject_reason       TEXT NOT NULL,
    raw_record          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_errors (
    error_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source_file     TEXT,
    stage           TEXT NOT NULL,
    error_message   TEXT NOT NULL,
    occurred_at     TEXT NOT NULL
);

-- ---------- curated tables ----------
CREATE TABLE IF NOT EXISTS dim_customers (
    customer_id         TEXT PRIMARY KEY,
    full_name           TEXT NOT NULL,
    email               TEXT NOT NULL,
    country             TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    run_id              TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source_file         TEXT NOT NULL,
    source_row_number   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_products (
    product_id          TEXT PRIMARY KEY,
    product_name        TEXT NOT NULL,
    category            TEXT NOT NULL,
    list_price_cents    INTEGER NOT NULL CHECK (list_price_cents >= 0),
    updated_at          TEXT NOT NULL,
    run_id              TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source_file         TEXT NOT NULL,
    source_row_number   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_orders (
    order_id            TEXT PRIMARY KEY,
    customer_id         TEXT NOT NULL REFERENCES dim_customers(customer_id),
    product_id          TEXT NOT NULL REFERENCES dim_products(product_id),
    quantity            INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents    INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    line_total_cents    INTEGER NOT NULL,
    order_status        TEXT NOT NULL
                        CHECK (order_status IN ('placed', 'shipped', 'cancelled', 'returned')),
    order_ts            TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    run_id              TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source_file         TEXT NOT NULL,
    source_row_number   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS order_status_history (
    order_id            TEXT NOT NULL,
    order_status        TEXT NOT NULL,
    event_ts            TEXT NOT NULL,
    run_id              TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source_file         TEXT NOT NULL,
    source_row_number   INTEGER NOT NULL,
    PRIMARY KEY (order_id, event_ts)
);

CREATE INDEX IF NOT EXISTS idx_fact_orders_customer ON fact_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_fact_orders_product ON fact_orders(product_id);
CREATE INDEX IF NOT EXISTS idx_fact_orders_run ON fact_orders(run_id);
CREATE INDEX IF NOT EXISTS idx_rejected_run_reason ON rejected_records(run_id, reject_reason);
"""


def connect(db_path):
       """Open the SQLite database (creating its folder) with foreign keys enforced."""
       path = Path(db_path)
       path.parent.mkdir(parents=True, exist_ok=True)
       conn = sqlite3.connect(path)
       conn.execute("PRAGMA foreign_keys = ON")
       conn.execute("PRAGMA cache_size = -65536")  # 64 MB page cache (negative = KiB)
       return conn


def init_db(conn):
    """Create all tables. Safe to call repeatedly (IF NOT EXISTS)."""
    conn.executescript(DDL)