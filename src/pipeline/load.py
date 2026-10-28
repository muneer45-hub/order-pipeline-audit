"""Loading validated rows into the curated tables.

Idempotent: every load is an upsert on the business key, so loading the same data
twice never creates duplicates. A row only replaces an existing one if its updated_at
is strictly newer. Older or equal versions come back as "stale" (late-arriving data)
and the runner records them as rejects instead of overwriting.

Table and column names below are constants defined in this file, never user input.
"""

LINEAGE = ["run_id", "source_file", "source_row_number"]

HISTORY_SQL = (
    "INSERT OR IGNORE INTO order_status_history "
    "(order_id, order_status, event_ts, run_id, source_file, source_row_number) "
    "VALUES (:order_id, :order_status, :updated_at, :run_id, :source_file, :source_row_number)"
)


def _upsert(conn, table, key, data_columns, run_id, source_file, accepted):
    existing = dict(conn.execute(f"SELECT {key}, updated_at FROM {table}"))
    fresh, stale = [], []
    for row_number, record in accepted:
        current = existing.get(record[key])
        if current is not None and record["updated_at"] <= current:
            stale.append((row_number, record[key]))
        else:
            fresh.append((row_number, record))

    columns = data_columns + LINEAGE
    placeholders = ", ".join(f":{c}" for c in columns)
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != key)
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT({key}) DO UPDATE SET {updates} "
        f"WHERE excluded.updated_at > {table}.updated_at"
    )
    rows = [dict(record, run_id=run_id, source_file=source_file, source_row_number=number)
            for number, record in fresh]
    conn.executemany(sql, rows)
    return fresh, stale


def load_customers(conn, run_id, source_file, accepted):
    """Returns (rows_loaded, stale) where stale = [(row_number, key), ...]."""
    fresh, stale = _upsert(
        conn, "dim_customers", "customer_id",
        ["customer_id", "full_name", "email", "country", "updated_at"],
        run_id, source_file, accepted)
    return len(fresh), stale


def load_products(conn, run_id, source_file, accepted):
    fresh, stale = _upsert(
        conn, "dim_products", "product_id",
        ["product_id", "product_name", "category", "list_price_cents", "updated_at"],
        run_id, source_file, accepted)
    return len(fresh), stale


def load_orders(conn, run_id, source_file, accepted):
    fresh, stale = _upsert(
        conn, "fact_orders", "order_id",
        ["order_id", "customer_id", "product_id", "quantity", "unit_price_cents",
         "line_total_cents", "order_status", "order_ts", "updated_at"],
        run_id, source_file, accepted)
    # History is append-only: every accepted version of an order adds a status event.
    conn.executemany(HISTORY_SQL, [
        dict(record, run_id=run_id, source_file=source_file, source_row_number=number)
        for number, record in fresh])
    return len(fresh), stale