# Design Note

## 1. Problem
A batch pipeline that ingests order data from CSV files, validates it, quarantines bad
records, loads clean data into SQLite, and records a full audit trail (run IDs, input
files, row counts, rejects, errors, output locations, timestamps) that can be queried to
trace every output row back to its source file and row.

## 2. Source files (data/raw)
| File | Grain | Primary key |
|---|---|---|
| customers.csv | one row per customer version | customer_id |
| products.csv | one row per product version | product_id |
| orders.csv | one row per order | order_id |

## 3. Data dictionary

### customers.csv
| Column | Type | Rules |
|---|---|---|
| customer_id | text | required, unique, format C + 6 digits |
| full_name | text | required |
| email | text | required, must contain "@" |
| country | text | required, 2-letter code |
| updated_at | text | required, ISO-8601 UTC timestamp |

### products.csv
| Column | Type | Rules |
|---|---|---|
| product_id | text | required, unique, format P + 5 digits |
| product_name | text | required |
| category | text | required |
| list_price | decimal | required, >= 0 |
| updated_at | text | required, ISO-8601 UTC timestamp |

### orders.csv
| Column | Type | Rules |
|---|---|---|
| order_id | text | required, unique, format O + 8 digits |
| customer_id | text | required, must exist in customers (referential integrity) |
| product_id | text | required, must exist in products (referential integrity) |
| quantity | integer | required, > 0 |
| unit_price | decimal | required, >= 0 |
| order_status | text | required, one of: placed, shipped, cancelled, returned |
| order_ts | text | required, ISO-8601 UTC timestamp, not in the future |
| updated_at | text | required, ISO-8601 UTC timestamp |

## 4. Output (curated) tables
All curated tables carry `run_id` and `source_file` and `source_row_number` for lineage.
- `dim_customers`: latest valid version of each customer
- `dim_products`: latest valid version of each product
- `fact_orders`: latest valid version of each order, plus derived `line_total = quantity * unit_price`
- `order_status_history`: append-only log of every status change (history is preserved, not overwritten)
   - Money is stored as integer cents (`list_price_cents`, `unit_price_cents`, `line_total_cents`) so
     sums reconcile exactly; the CSV inputs carry decimal prices with at most 2 decimals.

## 5. Audit tables
- `pipeline_runs`: run_id, status (running/success/failed), started_at, ended_at, rows_read, rows_loaded, rows_rejected, failure_reason
- `run_input_files`: run_id, source_file, file_checksum, row_count
- `rejected_records`: run_id, source_file, source_row_number, raw_record, reject_reason
- `run_errors`: run_id, stage, error_message, occurred_at

## 6. Naming conventions
- snake_case for all tables and columns
- ISO-8601 UTC timestamps (e.g. 2026-10-28T12:30:00Z)
- run_id format: run_YYYYMMDDTHHMMSSZ_<short random suffix>
- Deterministic IDs: business keys come from the source; audit keys are derived from file checksum + row number

## 7. Key business rules (decisions)
- Duplicate key in the same batch: keep the row with the latest updated_at, reject the others as `duplicate_key`.
- Late-arriving data: if an incoming row has an older updated_at than what is already loaded, it is rejected as `stale_update` and does not overwrite.
- Invalid reference: an order pointing to a missing customer or product is quarantined as `invalid_customer_ref` / `invalid_product_ref`.
- Rerun of the same file (same checksum): skipped and logged, so no duplicates are created.

## 8. Assumptions
- - Input files are UTF-8 CSV with a header row whose columns match the expected order exactly.
  Any other header is treated as a schema change and the file fails (see tests).
- All timestamps are UTC in `YYYY-MM-DDTHH:MM:SSZ` form; anything else is `invalid_timestamp`.
- `updated_at` from the source is trustworthy and decides which version of a record is newest.
- IDs follow fixed formats (C + 6 digits, P + 5 digits, O + 8 digits).
- Prices have at most 2 decimals. `unit_price` is the price charged at order time and is not
  compared with the product's current `list_price`.
- Customers and products are reference data and are loaded before orders. An order whose
  customer or product is not valid is rejected, not loaded.
- Each file is a batch of full records. Deletions are not modelled.
- "In the future" for `order_ts` means later than the moment the run started.
- Data is synthetic; no personal or real data is used.

## 9. Trade-offs and limitations
- - **SQLite instead of a server database.** Zero setup and runnable anywhere, which the task asks for,
  but only one writer at a time and no lock against two simultaneous runs.
- **Standard-library `csv` instead of pandas.** Fewer dependencies and exact row numbers for every
  reject (traceability), but slower than vectorised validation. This is the main performance
  limit (see the Performance section).
- **One reject reason per row.** Rules are checked in a fixed order and the first failure wins.
  Deterministic and easy to test, but a row with two problems shows only one.
- **Idempotency by file checksum.** Simple and safe for reruns. A corrected file with different
  content counts as new; its rows are then protected by the `updated_at` comparison.
- **One transaction per file, not per run.** A failure affects only that file and a retry resumes
  where it stopped. The cost is that a run can end with some files loaded and some failed, which
  the run status (`failed`) and per-file status make visible.
- **Stale rows are quarantined, not merged into history.** Prevents silent overwrites, but an older
  version of an order that arrives late is not preserved in `order_status_history`.
- **Each file is read fully into memory.** Fine for 100k+ rows; a much larger file needs chunking.
- **Timings** come from three interleaved runs on one laptop and are indicative, not a benchmark.

## 10. Performance

**Setup:** 106,118 input rows (5,055 customers, 508 products, 100,555 orders, about 5% deliberately
bad) generated with seed 42, loaded into a fresh SQLite database on a Windows laptop
(Python 3.13). Reproduce with `python scripts/compare_optimizations.py --input-dir data/large`.

**Method:** I profiled first (`python scripts/benchmark.py --input-dir data/large --profile`)
instead of guessing. Profiling showed validation as the biggest Python cost, with
`datetime.strptime` called about 200,000 times (two timestamps per order), and SQLite batch
inserts as the other large cost. I then compared variants in one process, interleaving the
runs (round 1 of every variant, then round 2, and so on) so machine noise affects all
variants equally. Each variant ran 3 times.

| Variant | Median | Best | Speedup |
|---|---|---|---|
| Baseline | 16.99 s | 15.23 s | 1.00x |
| A: 64 MB SQLite page cache (`PRAGMA cache_size`) | 12.01 s | 11.74 s | 1.41x |
| B: slice-based timestamp parsing instead of `strptime` | 12.70 s | 12.35 s | 1.34x |
| A + B (shipped) | 8.82 s | 8.77 s | 1.93x |

Row counts were identical for every variant (read 106,118; loaded 100,843; rejected 5,275),
and all 27 tests pass with the optimizations on.

**Why these two:**
- B removes redundant work. The regex has already fixed the timestamp layout, so building the
  `datetime` directly gives the same result without the slow `strptime` machinery. `datetime()`
  still rejects impossible dates such as month 13.
- A is motivated by random key order. Orders arrive shuffled, so inserts touch random pages of
  several indexes, and SQLite's default cache is small, so pages get evicted and reloaded.
  The measured gain is consistent with that explanation, but I did not isolate the cause with
  a separate cache-miss measurement.

**Limits of these measurements:** 3 runs per variant on one laptop; run-to-run noise was about
+/-2 s, which is why variants were interleaved and compared by median. Throughput after
optimization is roughly 12,000 rows/s.

**Next optimization ideas (not done):** validate with vectorised or batched checks, drop the
`raw_record` JSON for accepted rows (already the case) and insert rejects in bulk, process the
input in chunks to cap memory, and parallelise independent files.