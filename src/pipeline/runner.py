"""Pipeline orchestration. One run = one pass over the input files.

Each file is processed in its own transaction:
- success: everything for that file is committed together (data, rejects, audit rows)
- failure: the file's transaction is rolled back, the failure is recorded, and the run
  continues with the other files (partial failure)
A rerun skips files whose checksum was already processed and retries failed ones,
so retry and restart are the same command.
"""
import json
from pathlib import Path

from . import audit
from .config import ENTITIES
from .ingest import SchemaError, file_checksum, read_csv
from .load import load_customers, load_orders, load_products
from .schema import connect, init_db
from .validate import Reject, validate_batch

LOADERS = {"customers": load_customers, "products": load_products, "orders": load_orders}
UPSTREAM = ("customers", "products")  # orders depend on these


def _file_result(source_file, status, row_count=0, loaded=0, rejected=0, reason=None):
    return {"source_file": source_file, "file_status": status, "row_count": row_count,
            "rows_loaded": loaded, "rows_rejected": rejected, "failure_reason": reason}


def _references(conn):
    return {
        "customer_id": {r[0] for r in conn.execute("SELECT customer_id FROM dim_customers")},
        "product_id": {r[0] for r in conn.execute("SELECT product_id FROM dim_products")},
    }


def _process_file(conn, run_id, entity, input_dir, now):
    spec = ENTITIES[entity]
    path = Path(input_dir) / spec["file"]
    checksum = file_checksum(path)

    if conn.execute("SELECT 1 FROM processed_files WHERE file_checksum = ?",
                    (checksum,)).fetchone():
        result = _file_result(spec["file"], "skipped_already_processed")
        audit.record_file(conn, run_id, entity, path, checksum, result)
        conn.commit()
        return result

    rows = read_csv(path, spec["columns"])  # may raise SchemaError
    refs = _references(conn) if entity == "orders" else {}
    accepted, rejected = validate_batch(entity, rows, now, refs)
    loaded, stale = LOADERS[entity](conn, run_id, spec["file"], accepted)

    if stale:
        raw_by_row = dict(rows)
        rejected += [Reject(n, key, "stale_update", json.dumps(raw_by_row[n]))
                     for n, key in stale]
    audit.record_rejects(conn, run_id, spec["file"], rejected)

    result = _file_result(spec["file"], "loaded", len(rows), loaded, len(rejected))
    audit.record_file(conn, run_id, entity, path, checksum, result)
    audit.mark_processed(conn, checksum, spec["file"], run_id, audit.iso(audit.utc_now()))
    conn.commit()
    return result


def _record_failure(conn, run_id, entity, input_dir, stage, message):
    spec = ENTITIES[entity]
    path = Path(input_dir) / spec["file"]
    try:
        checksum = file_checksum(path)
    except OSError:
        checksum = "n/a"
    result = _file_result(spec["file"], "failed", reason=message)
    audit.record_file(conn, run_id, entity, path, checksum, result)
    audit.log_error(conn, run_id, spec["file"], stage, message, audit.iso(audit.utc_now()))
    conn.commit()
    return result


def run_pipeline(input_dir, db_path, now=None):
    """Run the pipeline once and return a summary dict.

    now: the moment used for the "order date is in the future" rule (injectable for tests).
    """
    started = audit.utc_now()
    now = now or started
    run_id = audit.new_run_id(started)

    conn = connect(db_path)
    try:
        init_db(conn)
        audit.start_run(conn, run_id, input_dir, audit.iso(started))

        files, failed_upstream = [], []
        for entity in ENTITIES:
            source_file = ENTITIES[entity]["file"]
            if entity == "orders" and failed_upstream:
                message = f"skipped: upstream file failed ({', '.join(failed_upstream)})"
                files.append(_record_failure(conn, run_id, entity, input_dir,
                                             "dependency", message))
                continue
            try:
                result = _process_file(conn, run_id, entity, input_dir, now)
            except SchemaError as exc:
                conn.rollback()
                result = _record_failure(conn, run_id, entity, input_dir,
                                         "schema_check", str(exc))
            except Exception as exc:  # any other failure: roll back this file only
                conn.rollback()
                result = _record_failure(conn, run_id, entity, input_dir, "processing",
                                         f"{type(exc).__name__}: {exc}")
            if result["file_status"] == "failed" and entity in UPSTREAM:
                failed_upstream.append(source_file)
            files.append(result)

        failed = [f for f in files if f["file_status"] == "failed"]
        summary = {
            "run_id": run_id,
            "status": "failed" if failed else "success",
            "rows_read": sum(f["row_count"] for f in files),
            "rows_loaded": sum(f["rows_loaded"] for f in files),
            "rows_rejected": sum(f["rows_rejected"] for f in files),
            "failure_reason": "; ".join(f"{f['source_file']}: {f['failure_reason']}"
                                        for f in failed) or None,
            "files": files,
        }
        audit.finish_run(conn, run_id, summary["status"], audit.iso(audit.utc_now()),
                         summary["rows_read"], summary["rows_loaded"],
                         summary["rows_rejected"], summary["failure_reason"])
        return summary
    finally:
        conn.close()