# order-pipeline-audit

A small batch data pipeline that ingests order data from CSV files, validates it, quarantines bad
records, loads clean data into SQLite and records a full **audit trail**: run IDs, input files
(with checksums), row counts, rejects, errors, timestamps and output locations. A queryable audit
report links every output row back to its source file and row.

Built for the YottaFlex AI 72-hour data engineering challenge (Python, SQLite, pytest).

## What it does

```
data/*.csv  ->  ingest  ->  validate  ->  load (upsert)  ->  curated tables
                  |            |             |
              checksum      rejects       audit tables  ->  audit report / order trace
              + schema      quarantined   (runs, files, rejects, errors)
```

- **Ingest:** reads `customers.csv`, `products.csv`, `orders.csv`, computes a SHA-256 checksum per
  file and checks the header against the expected schema.
- **Validate:** required fields, formats, value ranges, business rules, referential integrity and
  duplicate handling. Every rejected row gets exactly one reason and stays traceable to its source
  file and row number.
- **Load:** idempotent upserts into `dim_customers`, `dim_products`, `fact_orders`, plus an
  append-only `order_status_history`. Every curated row carries `run_id`, `source_file` and
  `source_row_number`.
- **Audit:** `pipeline_runs`, `run_input_files`, `rejected_records`, `run_errors`,
  `processed_files`.
- **Report:** run history, reject breakdown, lineage counts, aggregates and 9 reconciliation
  checks, plus a `trace` command that follows one order back to its source row.

## Quick start

Requires Python 3.10 or newer. Tested on Windows with Python 3.13.

```bash
git clone https://github.com/muneer45-hub/order-pipeline-audit.git
cd order-pipeline-audit
python -m venv .venv
```

Activate the environment:

- Windows (PowerShell): `.venv\Scripts\activate`
  (if scripts are blocked: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`)
- macOS / Linux: `source .venv/bin/activate`

```bash
pip install -r requirements.txt     # installs pytest and this package in editable mode
python -m pytest -q                 # expected: 27 passed
python -m pipeline.cli run --input-dir data/sample --db output/pipeline.db
python -m pipeline.cli run --input-dir data/sample --db output/pipeline.db   # rerun: all files skipped
python -m pipeline.cli report --db output/pipeline.db --out reports/audit_report.md
python -m pipeline.cli trace --db output/pipeline.db --order-id O00000003
```

No external services, credentials or network access are needed.

## Commands

| Command | Purpose |
|---|---|
| `python -m pipeline.cli run --input-dir DIR --db FILE` | Process the three CSV files once. Exit code 0 on success, 1 if any file failed. |
| `python -m pipeline.cli report --db FILE [--out FILE.md]` | Print the audit report and run all reconciliation checks. Exit code 1 if a check fails. |
| `python -m pipeline.cli trace --db FILE --order-id ID` | Show where one order came from: file, row, checksum, run, status history, rejected versions. |
| `python scripts/generate_data.py --out-dir DIR [options]` | Generate synthetic data with a fixed seed. |
| `python scripts/benchmark.py --input-dir DIR [--profile]` | Time one run, optionally with a cProfile table. |
| `python scripts/compare_optimizations.py --input-dir DIR` | Compare optimisation variants fairly (interleaved runs). |

## Data

Synthetic only. No real or personal data is used.

- `data/sample/`: small starter set (100 customers, 30 products, 300 orders plus injected bad rows),
  committed so reviewers can run immediately.
- `data/sample_expected/expected_rejects.csv`: the **answer key**, kept in a separate folder from the
  input. It lists which rows are deliberately bad and why. The pipeline never reads it; tests use it
  to prove the validator catches exactly those rows.
- Larger run (not committed, about 106k rows):

```bash
python scripts/generate_data.py --out-dir data/large --customers 5000 --products 500 --orders 100000
python -m pipeline.cli run --input-dir data/large --db output/large.db
```

The generator injects about 5% bad records: missing fields, malformed rows, invalid emails, prices
and quantities, invalid customer and product references, future timestamps, invalid statuses and
duplicate keys. Rows are shuffled, so duplicates and older versions arrive out of order. A fixed
`--seed` (default 42) makes the output reproducible.

## Tests

```bash
python -m pytest -q
```

27 tests cover: schema creation and idempotent init; the answer-key test (validator output equals
the injected bad rows exactly); happy path; rerun of the same input; empty batch (header only);
completely empty file; unexpected schema change; nulls and malformed rows; seven invalid-order
cases (bad references, quantity, price, future date, short row, missing field); duplicate keys
arriving out of order; late-arriving older data not overwriting newer data; status history kept;
partial failure with rollback and a successful retry; end-to-end reconciliation on the sample;
the report checks pass on clean data and **fail on deliberately corrupted data**; order trace;
and CLI exit codes.

## Results

On the sample data the audit report is in [`reports/audit_report.md`](reports/audit_report.md) and
an example lineage trace is in [`reports/trace_example.txt`](reports/trace_example.txt).

On the large run (106,118 rows: 5,055 customers, 508 products, 100,555 orders):

| File | Read | Loaded | Rejected |
|---|---|---|---|
| customers.csv | 5,055 | 4,805 | 250 |
| products.csv | 508 | 483 | 25 |
| orders.csv | 100,555 | 95,555 | 5,000 |

For every file, read = loaded + rejected, and the report's reconciliation checks pass.

Performance (details in [DESIGN.md](DESIGN.md)): median 16.99 s at baseline and 8.82 s after the
two optimisations (a larger SQLite page cache and faster timestamp parsing), a 1.93x speedup, with
identical results.

## Repository layout

```
src/pipeline/   config, schema, ingest, validate, load, audit, runner, report, cli
scripts/        generate_data.py, benchmark.py, compare_optimizations.py
tests/          pytest suite
data/sample/    committed starter data;  data/sample_expected/  answer key (separate)
reports/        generated audit report and trace example
DESIGN.md       design note, data dictionary, trade-offs, performance, Azure mapping
AI_USAGE.md     how AI was used;  PROMPTS.md  full prompt history
```

## Key design decisions

Full reasoning is in [DESIGN.md](DESIGN.md). In short:

- **One transaction per file.** A failure rolls back only that file; earlier files stay committed
  and the failure is recorded with its reason. Orders are skipped if customers or products failed,
  to avoid thousands of misleading "invalid reference" rejects.
- **Idempotent, with retry = rerun.** Files are identified by checksum; loaded files are skipped,
  failed files are retried, and loads are upserts on the business key.
- **Late-arriving data.** A row only replaces an existing one if its `updated_at` is strictly newer;
  otherwise it is quarantined as `stale_update`.
- **History preserved.** Order status changes are appended to `order_status_history`.
- **Money as integer cents** so totals reconcile exactly.
- **Naming:** snake_case, ISO-8601 UTC timestamps, run IDs like `run_20261028T075754Z_57d3a8`.

## Retry, restart and backfill

- **Retry / restart:** run the same command again. Already loaded files are skipped by checksum,
  failed files are processed again. A run left as `running` (process killed) is flagged by the
  `no_interrupted_runs` check.
- - **Backfill:** put older data in a new folder and run with `--input-dir`. Rows older than what is
  already loaded cannot overwrite newer ones; they are quarantined as `stale_update` (not applied,
  not added to history). Every version that is applied is kept in `order_status_history`.

## Known limitations

- SQLite allows one writer at a time; there is no lock to stop two pipeline runs starting together.
- Each file is read fully into memory before validation. Fine for 100k+ rows; a much larger file
  would need chunked processing.
- The idempotency key is the file checksum. A corrected file with different content is processed as
  new, and its rows are protected by `updated_at` comparison, not by file name.
- Deletions in the source are not detected (the model is insert and update only).
- Order status history is keyed by `(order_id, updated_at)`, so two different statuses with the
- Late-arriving older versions of an order are quarantined, not merged into its status history, so
  the history only contains versions that were applied.
  same timestamp keep only the first.
- The "order date is in the future" rule uses the time the run started.
- Timings come from three runs on one laptop and are indicative only.

## Possible next steps

Chunked and parallel file processing, batched validation, a run lock, a schema-evolution policy
(for example accept new optional columns), alerting on failed runs, and an Azure deployment
(see the mapping in DESIGN.md).

## AI use

AI assistance (Claude) was used for planning, code drafts and step-by-step guidance. See
[AI_USAGE.md](AI_USAGE.md) for what I decided, reviewed and validated, and
[PROMPTS.md](PROMPTS.md) for the full prompt history.