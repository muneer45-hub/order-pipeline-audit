"""Audit report: run history, rejects, lineage, aggregates and reconciliation checks.

Also provides trace_order(): follow one output row back to its source file, row number,
run and file checksum. All SQL below is constant text (no user input is interpolated,
the order id is passed as a bound parameter).
"""

LINEAGE_TABLES = ("fact_orders", "dim_customers", "dim_products")


def _lineage_violations_sql():
    parts = [
        f"(SELECT COUNT(*) FROM {t} x WHERE NOT EXISTS ("
        "SELECT 1 FROM run_input_files f WHERE f.run_id = x.run_id "
        "AND f.source_file = x.source_file AND f.file_status = 'loaded'))"
        for t in LINEAGE_TABLES
    ]
    return "SELECT " + " + ".join(parts)


# (name, description, SQL returning the number of violations; 0 means the check passes)
CHECKS = [
    ("source_to_target_counts",
     "every loaded file: rows read = rows loaded + rows rejected",
     "SELECT COUNT(*) FROM run_input_files WHERE file_status = 'loaded' "
     "AND row_count != rows_loaded + rows_rejected"),
    ("rejects_are_traceable",
     "every loaded file: rows in rejected_records = rows_rejected",
     "SELECT COUNT(*) FROM run_input_files f WHERE f.file_status = 'loaded' "
     "AND f.rows_rejected != (SELECT COUNT(*) FROM rejected_records r "
     "WHERE r.run_id = f.run_id AND r.source_file = f.source_file)"),
    ("run_totals_match_files",
     "every finished run: run totals = sum of its file totals",
     "SELECT COUNT(*) FROM pipeline_runs r WHERE r.status != 'running' AND ("
     "r.rows_read != (SELECT COALESCE(SUM(row_count), 0) FROM run_input_files f WHERE f.run_id = r.run_id) "
     "OR r.rows_loaded != (SELECT COALESCE(SUM(rows_loaded), 0) FROM run_input_files f WHERE f.run_id = r.run_id) "
     "OR r.rows_rejected != (SELECT COALESCE(SUM(rows_rejected), 0) FROM run_input_files f WHERE f.run_id = r.run_id))"),
    ("no_orphan_customer_refs",
     "orders whose customer_id is missing from dim_customers",
     "SELECT COUNT(*) FROM fact_orders o LEFT JOIN dim_customers c "
     "ON c.customer_id = o.customer_id WHERE c.customer_id IS NULL"),
    ("no_orphan_product_refs",
     "orders whose product_id is missing from dim_products",
     "SELECT COUNT(*) FROM fact_orders o LEFT JOIN dim_products p "
     "ON p.product_id = o.product_id WHERE p.product_id IS NULL"),
    ("line_total_is_quantity_times_price",
     "orders where line_total_cents != quantity * unit_price_cents",
     "SELECT COUNT(*) FROM fact_orders WHERE line_total_cents != quantity * unit_price_cents"),
    ("lineage_is_complete",
     "curated rows not linked to a loaded input file in the audit tables",
     _lineage_violations_sql()),
    ("history_matches_current_status",
     "orders whose current status has no matching history event",
     "SELECT COUNT(*) FROM fact_orders o WHERE NOT EXISTS (SELECT 1 FROM order_status_history h "
     "WHERE h.order_id = o.order_id AND h.event_ts = o.updated_at AND h.order_status = o.order_status)"),
    ("no_interrupted_runs",
     "runs still marked 'running' (the process stopped without finishing)",
     "SELECT COUNT(*) FROM pipeline_runs WHERE status = 'running'"),
]


def run_checks(conn):
    """Return [(name, passed, detail)]."""
    results = []
    for name, description, sql in CHECKS:
        violations = conn.execute(sql).fetchone()[0]
        results.append((name, violations == 0, f"{description} ({violations} violation(s))"))
    return results


def _dicts(cursor):
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def trace_order(conn, order_id):
    """Follow one order back to its source. Returns None if the order is not loaded."""
    order = _dicts(conn.execute(
        "SELECT o.order_id, o.customer_id, o.product_id, o.quantity, o.unit_price_cents, "
        "o.line_total_cents, o.order_status, o.updated_at, o.run_id, o.source_file, "
        "o.source_row_number, r.started_at AS run_started_at, f.file_path, f.file_checksum "
        "FROM fact_orders o JOIN pipeline_runs r ON r.run_id = o.run_id "
        "LEFT JOIN run_input_files f ON f.run_id = o.run_id AND f.source_file = o.source_file "
        "WHERE o.order_id = ?", (order_id,)))
    if not order:
        return None
    history = _dicts(conn.execute(
        "SELECT order_status, event_ts, run_id, source_file, source_row_number "
        "FROM order_status_history WHERE order_id = ? ORDER BY event_ts", (order_id,)))
    rejects = _dicts(conn.execute(
        "SELECT run_id, source_file, source_row_number, reject_reason "
        "FROM rejected_records WHERE record_key = ? ORDER BY rowid", (order_id,)))
    return {"order": order[0], "history": history, "rejects": rejects}


def format_trace(trace):
    o = trace["order"]
    lines = [
        f"Order {o['order_id']}  status={o['order_status']}  customer={o['customer_id']}  "
        f"product={o['product_id']}",
        f"  quantity={o['quantity']}  unit_price_cents={o['unit_price_cents']}  "
        f"line_total_cents={o['line_total_cents']}",
        "Loaded from:",
        f"  file      {o['source_file']}  (row {o['source_row_number']})",
        f"  path      {o['file_path']}",
        f"  checksum  {o['file_checksum']}",
        f"  run       {o['run_id']}  started {o['run_started_at']}",
        "Status history:",
    ]
    for h in trace["history"]:
        lines.append(f"  {h['event_ts']}  {h['order_status']:<10} "
                     f"{h['source_file']} row {h['source_row_number']}  ({h['run_id']})")
    if trace["rejects"]:
        lines.append("Rejected versions of this order:")
        for r in trace["rejects"]:
            lines.append(f"  {r['source_file']} row {r['source_row_number']}: "
                         f"{r['reject_reason']}  ({r['run_id']})")
    return "\n".join(lines)


def _table(headers, rows):
    if not rows:
        return "_none_\n"
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def _money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def build_report(conn):
    """Return (markdown_text, all_checks_passed)."""
    q = lambda sql: conn.execute(sql).fetchall()
    out = ["# Pipeline audit report", ""]

    out += ["## Run history (last 10 runs)", _table(
        ["run_id", "status", "started_at", "ended_at", "read", "loaded", "rejected", "failure"],
        q("SELECT run_id, status, started_at, COALESCE(ended_at, ''), rows_read, rows_loaded, "
          "rows_rejected, COALESCE(failure_reason, '') FROM ("
          "SELECT rowid AS rid, * FROM pipeline_runs ORDER BY rowid DESC LIMIT 10) ORDER BY rid"))]

    out += ["## Files in the latest run", _table(
        ["source_file", "status", "read", "loaded", "rejected", "failure"],
        q("SELECT source_file, file_status, row_count, rows_loaded, rows_rejected, "
          "COALESCE(failure_reason, '') FROM run_input_files WHERE run_id = "
          "(SELECT run_id FROM pipeline_runs ORDER BY rowid DESC LIMIT 1) ORDER BY rowid"))]

    out += ["## Reject breakdown (all runs)", _table(
        ["source_file", "reject_reason", "rows"],
        q("SELECT source_file, reject_reason, COUNT(*) FROM rejected_records "
          "GROUP BY source_file, reject_reason ORDER BY source_file, COUNT(*) DESC, reject_reason"))]

    out += ["## Lineage: output rows per source file and run", _table(
        ["table", "source_file", "run_id", "rows"],
        q(" UNION ALL ".join(
            f"SELECT '{t}', source_file, run_id, COUNT(*) FROM {t} GROUP BY source_file, run_id"
            for t in LINEAGE_TABLES) + " ORDER BY 1, 3"))]

    status_rows = [(s, n, _money(total)) for s, n, total in q(
        "SELECT order_status, COUNT(*), COALESCE(SUM(line_total_cents), 0) FROM fact_orders "
        "GROUP BY order_status ORDER BY order_status")]
    out += ["## Key aggregates: orders by status", _table(
        ["order_status", "orders", "revenue"], status_rows)]

    results = run_checks(conn)
    out += ["## Reconciliation and integrity checks", _table(
        ["check", "result", "detail"],
        [(name, "PASS" if ok else "FAIL", detail) for name, ok, detail in results])]
    all_passed = all(ok for _, ok, _ in results)
    out += [f"**Overall: {'ALL CHECKS PASSED' if all_passed else 'CHECKS FAILED'}**", ""]
    return "\n".join(out), all_passed