"""Benchmark the pipeline on a fresh temporary database.

    python scripts/benchmark.py --input-dir data/large
    python scripts/benchmark.py --input-dir data/large --profile
"""
import argparse
import cProfile
import pstats
import tempfile
import time
from pathlib import Path

from pipeline.runner import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Time one pipeline run")
    parser.add_argument("--input-dir", default="data/large")
    parser.add_argument("--profile", action="store_true",
                        help="also print the 15 most expensive functions (cProfile)")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "bench.db"  # fresh database each time, so nothing is skipped
        profiler = cProfile.Profile() if args.profile else None
        start = time.perf_counter()
        if profiler:
            summary = profiler.runcall(run_pipeline, args.input_dir, db)
        else:
            summary = run_pipeline(args.input_dir, db)
        elapsed = time.perf_counter() - start

    rows = summary["rows_read"]
    print(f"status={summary['status']} rows_read={rows} loaded={summary['rows_loaded']} "
          f"rejected={summary['rows_rejected']}")
    print(f"elapsed={elapsed:.2f}s  throughput={rows / elapsed:,.0f} rows/s")
    if profiler:
        print("\nTop 15 functions by cumulative time:")
        pstats.Stats(profiler).sort_stats("cumulative").print_stats(15)


if __name__ == "__main__":
    main()