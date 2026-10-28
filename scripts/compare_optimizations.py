"""Compare optimisation variants fairly, in one process.

    python scripts/compare_optimizations.py --input-dir data/large --rounds 3

Variants are switched on and off by patching two functions, so no code has to be
edited or stashed between runs. Runs are interleaved (round 1 of every variant, then
round 2, ...) so machine noise affects all variants equally. Every variant must
produce identical row counts, otherwise an optimisation changed behaviour.
"""
import argparse
import sqlite3
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from pipeline import runner, validate
from pipeline.config import TS_FORMAT

CURRENT_CONNECT = runner.connect                  # 64 MB cache (optimisation A)
CURRENT_PARSE = validate.parse_timestamp          # direct slicing (optimisation B)


def connect_default_cache(db_path):
    """The original connect(): SQLite's default ~2 MB page cache."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def parse_timestamp_strptime(text):
    """The original parse_timestamp(): strptime after the regex check."""
    if not validate.TS_PATTERN.match(text):
        return None
    try:
        return datetime.strptime(text, TS_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


VARIANTS = {
    "baseline":            (connect_default_cache, parse_timestamp_strptime),
    "A cache only":        (CURRENT_CONNECT, parse_timestamp_strptime),
    "B timestamps only":   (connect_default_cache, CURRENT_PARSE),
    "A + B":               (CURRENT_CONNECT, CURRENT_PARSE),
}


def run_once(input_dir, connect_fn, parse_fn):
    runner.connect = connect_fn
    validate.parse_timestamp = parse_fn
    try:
        with tempfile.TemporaryDirectory() as tmp:
            start = time.perf_counter()
            summary = runner.run_pipeline(input_dir, Path(tmp) / "bench.db")
            elapsed = time.perf_counter() - start
    finally:
        runner.connect = CURRENT_CONNECT
        validate.parse_timestamp = CURRENT_PARSE
    return elapsed, (summary["status"], summary["rows_read"],
                     summary["rows_loaded"], summary["rows_rejected"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data/large")
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()

    times = {name: [] for name in VARIANTS}
    outcomes = set()
    for round_number in range(1, args.rounds + 1):
        for name, (connect_fn, parse_fn) in VARIANTS.items():
            elapsed, outcome = run_once(args.input_dir, connect_fn, parse_fn)
            times[name].append(elapsed)
            outcomes.add(outcome)
            print(f"round {round_number}  {name:<18} {elapsed:6.2f}s", flush=True)

    print()
    print(f"{'variant':<18} {'median':>8} {'best':>8}   all runs")
    base = statistics.median(times["baseline"])
    for name, values in times.items():
        median = statistics.median(values)
        runs = ", ".join(f"{v:.2f}" for v in values)
        print(f"{name:<18} {median:7.2f}s {min(values):7.2f}s   {runs}   "
              f"({base / median:.2f}x vs baseline)")

    print()
    if len(outcomes) == 1:
        status, read, loaded, rejected = next(iter(outcomes))
        print(f"Identical results in every run: status={status} read={read} "
              f"loaded={loaded} rejected={rejected}")
    else:
        print("WARNING: variants produced DIFFERENT results:", outcomes)


if __name__ == "__main__":
    main()