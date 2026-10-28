"""Row validation: structure, required fields, formats, business rules,
references and duplicates. Pure functions, no database access (easy to test).

Every rejected row gets exactly one reason, checked in a fixed order.
"""
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from .config import ENTITIES, TS_FORMAT

ID_PATTERNS = {
    "customer_id": re.compile(r"^C\d{6}$"),
    "product_id": re.compile(r"^P\d{5}$"),
    "order_id": re.compile(r"^O\d{8}$"),
}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")
TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
VALID_STATUSES = {"placed", "shipped", "cancelled", "returned"}


class Reject(NamedTuple):
    row_number: int
    record_key: str
    reason: str
    raw_record: str  # the original values as a JSON list


def parse_timestamp(text):
       """Strict ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ) or None.

       The regex fixes the layout, so the parts are sliced out directly. This is much
       faster than strptime. datetime() still rejects impossible dates such as month 13.
       """
       if not TS_PATTERN.match(text):
           return None
       try:
           return datetime(int(text[0:4]), int(text[5:7]), int(text[8:10]),
                           int(text[11:13]), int(text[14:16]), int(text[17:19]),
                           tzinfo=timezone.utc)
       except ValueError:
           return None


def parse_price_cents(text):
    """Non-negative price with at most 2 decimals -> integer cents, else None."""
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0:
        return None
    cents = value * 100
    if cents != cents.to_integral_value():
        return None
    return int(cents)


def parse_quantity(text):
    """Positive whole number or None."""
    if not text.isdigit():
        return None
    value = int(text)
    return value if value > 0 else None


def _has_missing(values):
    return any(v.strip() == "" for v in values)


def validate_customer(values, now, refs):
    if _has_missing(values):
        return "missing_required_field", None
    customer_id, full_name, email, country, updated_at = [v.strip() for v in values]
    if not ID_PATTERNS["customer_id"].match(customer_id):
        return "invalid_id_format", None
    if not EMAIL_PATTERN.match(email):
        return "invalid_email", None
    if not COUNTRY_PATTERN.match(country):
        return "invalid_country", None
    if parse_timestamp(updated_at) is None:
        return "invalid_timestamp", None
    return None, {"customer_id": customer_id, "full_name": full_name, "email": email,
                  "country": country, "updated_at": updated_at}


def validate_product(values, now, refs):
    if _has_missing(values):
        return "missing_required_field", None
    product_id, product_name, category, price_text, updated_at = [v.strip() for v in values]
    if not ID_PATTERNS["product_id"].match(product_id):
        return "invalid_id_format", None
    price_cents = parse_price_cents(price_text)
    if price_cents is None:
        return "invalid_price", None
    if parse_timestamp(updated_at) is None:
        return "invalid_timestamp", None
    return None, {"product_id": product_id, "product_name": product_name,
                  "category": category, "list_price_cents": price_cents,
                  "updated_at": updated_at}


def validate_order(values, now, refs):
    if _has_missing(values):
        return "missing_required_field", None
    (order_id, customer_id, product_id, quantity_text, price_text,
     status, order_ts, updated_at) = [v.strip() for v in values]
    if not (ID_PATTERNS["order_id"].match(order_id)
            and ID_PATTERNS["customer_id"].match(customer_id)
            and ID_PATTERNS["product_id"].match(product_id)):
        return "invalid_id_format", None
    quantity = parse_quantity(quantity_text)
    if quantity is None:
        return "invalid_quantity", None
    unit_price_cents = parse_price_cents(price_text)
    if unit_price_cents is None:
        return "invalid_price", None
    if status not in VALID_STATUSES:
        return "invalid_status", None
    order_dt = parse_timestamp(order_ts)
    if order_dt is None or parse_timestamp(updated_at) is None:
        return "invalid_timestamp", None
    if order_dt > now:
        return "future_order_ts", None
    if customer_id not in refs.get("customer_id", set()):
        return "invalid_customer_ref", None
    if product_id not in refs.get("product_id", set()):
        return "invalid_product_ref", None
    return None, {"order_id": order_id, "customer_id": customer_id, "product_id": product_id,
                  "quantity": quantity, "unit_price_cents": unit_price_cents,
                  "line_total_cents": quantity * unit_price_cents,
                  "order_status": status, "order_ts": order_ts, "updated_at": updated_at}


VALIDATORS = {
    "customers": validate_customer,
    "products": validate_product,
    "orders": validate_order,
}


def validate_batch(entity, rows, now, refs=None):
    """Validate one file's rows.

    rows: [(row_number, values)] from ingest.read_csv.
    refs: {"customer_id": set(...), "product_id": set(...)} of valid reference keys.
    Returns (accepted, rejected):
      accepted = [(row_number, record_dict)]  one row per key
      rejected = [Reject, ...] sorted by row number
    """
    refs = refs or {}
    spec = ENTITIES[entity]
    validator = VALIDATORS[entity]
    raw_by_row = {}
    valid, rejected = [], []

    for row_number, values in rows:
        raw = json.dumps(values)
        raw_by_row[row_number] = raw
        key = values[0].strip() if values else ""
        if len(values) != len(spec["columns"]):
            rejected.append(Reject(row_number, key, "malformed_row", raw))
            continue
        reason, record = validator(values, now, refs)
        if reason:
            rejected.append(Reject(row_number, key, reason, raw))
        else:
            valid.append((row_number, record))

    # Duplicate keys inside the batch: keep the latest updated_at (ties: later row).
    winner = {}
    for row_number, record in valid:
        key = record[spec["key"]]
        current = winner.get(key)
        if current is None or (record["updated_at"], row_number) > (current[1]["updated_at"], current[0]):
            winner[key] = (row_number, record)

    accepted = []
    for row_number, record in valid:
        key = record[spec["key"]]
        if winner[key][0] == row_number:
            accepted.append((row_number, record))
        else:
            rejected.append(Reject(row_number, key, "duplicate_key", raw_by_row[row_number]))

    rejected.sort(key=lambda r: r.row_number)
    return accepted, rejected