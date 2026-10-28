"""Audit trail: run lifecycle, per-file results, rejects and errors."""
import uuid
from datetime import datetime, timezone

from .config import TS_FORMAT


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(moment):
    return moment.strftime(TS_FORMAT)


def new_run_id(moment):
    """Sortable by time; the random suffix keeps two runs in one second distinct."""
    return f"run_{moment:%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"


def start_run(conn, run_id, input_dir, started_at):
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, status, started_at, input_dir) "
        "VALUES (?, 'running', ?, ?)",
        (run_id, started_at, str(input_dir)),
    )
    conn.commit()  # committed immediately, so a crash still leaves a 'running' record


def finish_run(conn, run_id, status, ended_at, rows_read, rows_loaded, rows_rejected,
               failure_reason):
    conn.execute(
        "UPDATE pipeline_runs SET status = ?, ended_at = ?, rows_read = ?, rows_loaded = ?, "
        "rows_rejected = ?, failure_reason = ? WHERE run_id = ?",
        (status, ended_at, rows_read, rows_loaded, rows_rejected, failure_reason, run_id),
    )
    conn.commit()


def record_file(conn, run_id, entity, path, checksum, result):
    conn.execute(
        "INSERT INTO run_input_files (run_id, source_file, entity, file_path, file_checksum, "
        "row_count, rows_loaded, rows_rejected, file_status, failure_reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, result["source_file"], entity, str(path), checksum, result["row_count"],
         result["rows_loaded"], result["rows_rejected"], result["file_status"],
         result["failure_reason"]),
    )


def record_rejects(conn, run_id, source_file, rejects):
    conn.executemany(
        "INSERT INTO rejected_records (run_id, source_file, source_row_number, record_key, "
        "reject_reason, raw_record) VALUES (?, ?, ?, ?, ?, ?)",
        [(run_id, source_file, r.row_number, r.record_key, r.reason, r.raw_record)
         for r in rejects],
    )


def mark_processed(conn, checksum, source_file, run_id, processed_at):
    conn.execute(
        "INSERT OR IGNORE INTO processed_files (file_checksum, source_file, run_id, processed_at) "
        "VALUES (?, ?, ?, ?)",
        (checksum, source_file, run_id, processed_at),
    )


def log_error(conn, run_id, source_file, stage, message, occurred_at):
    conn.execute(
        "INSERT INTO run_errors (run_id, source_file, stage, error_message, occurred_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (run_id, source_file, stage, message, occurred_at),
    )