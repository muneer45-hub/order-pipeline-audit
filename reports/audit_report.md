# Pipeline audit report

## Run history (last 10 runs)
| run_id | status | started_at | ended_at | read | loaded | rejected | failure |
|---|---|---|---|---|---|---|---|
| run_20261028T075536Z_d66ec9 | success | 2026-10-28T07:55:36Z | 2026-10-28T07:55:36Z | 431 | 410 | 21 |  |
| run_20261028T075707Z_c19e16 | success | 2026-10-28T07:57:07Z | 2026-10-28T07:57:07Z | 0 | 0 | 0 |  |

## Files in the latest run
| source_file | status | read | loaded | rejected | failure |
|---|---|---|---|---|---|
| customers.csv | skipped_already_processed | 0 | 0 | 0 |  |
| products.csv | skipped_already_processed | 0 | 0 | 0 |  |
| orders.csv | skipped_already_processed | 0 | 0 | 0 |  |

## Reject breakdown (all runs)
| source_file | reject_reason | rows |
|---|---|---|
| customers.csv | malformed_row | 2 |
| customers.csv | missing_required_field | 2 |
| customers.csv | invalid_email | 1 |
| orders.csv | invalid_status | 5 |
| orders.csv | future_order_ts | 2 |
| orders.csv | invalid_product_ref | 2 |
| orders.csv | malformed_row | 2 |
| orders.csv | duplicate_key | 1 |
| orders.csv | invalid_customer_ref | 1 |
| orders.csv | invalid_quantity | 1 |
| orders.csv | missing_required_field | 1 |
| products.csv | malformed_row | 1 |

## Lineage: output rows per source file and run
| table | source_file | run_id | rows |
|---|---|---|---|
| dim_customers | customers.csv | run_20261028T075536Z_d66ec9 | 95 |
| dim_products | products.csv | run_20261028T075536Z_d66ec9 | 29 |
| fact_orders | orders.csv | run_20261028T075536Z_d66ec9 | 286 |

## Key aggregates: orders by status
| order_status | orders | revenue |
|---|---|---|
| cancelled | 78 | 103204.98 |
| placed | 66 | 76579.98 |
| returned | 88 | 118336.59 |
| shipped | 54 | 63209.34 |

## Reconciliation and integrity checks
| check | result | detail |
|---|---|---|
| source_to_target_counts | PASS | every loaded file: rows read = rows loaded + rows rejected (0 violation(s)) |
| rejects_are_traceable | PASS | every loaded file: rows in rejected_records = rows_rejected (0 violation(s)) |
| run_totals_match_files | PASS | every finished run: run totals = sum of its file totals (0 violation(s)) |
| no_orphan_customer_refs | PASS | orders whose customer_id is missing from dim_customers (0 violation(s)) |
| no_orphan_product_refs | PASS | orders whose product_id is missing from dim_products (0 violation(s)) |
| line_total_is_quantity_times_price | PASS | orders where line_total_cents != quantity * unit_price_cents (0 violation(s)) |
| lineage_is_complete | PASS | curated rows not linked to a loaded input file in the audit tables (0 violation(s)) |
| history_matches_current_status | PASS | orders whose current status has no matching history event (0 violation(s)) |
| no_interrupted_runs | PASS | runs still marked 'running' (the process stopped without finishing) (0 violation(s)) |

**Overall: ALL CHECKS PASSED**
