"""Central configuration: expected input files, columns and keys.

Order matters: customers and products must load before orders, because
orders reference them (referential integrity).
"""
from pathlib import Path

TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DEFAULT_DB_PATH = Path("output/pipeline.db")
DEFAULT_INPUT_DIR = Path("data/sample")

ENTITIES = {
    "customers": {
        "file": "customers.csv",
        "key": "customer_id",
        "columns": ["customer_id", "full_name", "email", "country", "updated_at"],
    },
    "products": {
        "file": "products.csv",
        "key": "product_id",
        "columns": ["product_id", "product_name", "category", "list_price", "updated_at"],
    },
    "orders": {
        "file": "orders.csv",
        "key": "order_id",
        "columns": ["order_id", "customer_id", "product_id", "quantity", "unit_price",
                    "order_status", "order_ts", "updated_at"],
    },
}