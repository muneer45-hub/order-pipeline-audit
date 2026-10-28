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
- (to be completed as I build)

## 9. Trade-offs and limitations
- (to be completed at the end)

## 10. How this would map to Azure
- (to be completed at the end)