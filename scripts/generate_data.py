"""Synthetic data generator for the order pipeline.

Writes customers.csv, products.csv and orders.csv into --out-dir.
Deliberately bad records are injected (missing fields, invalid references,
duplicates, malformed rows, ...). The answer key of which rows are bad and why is
written to a SEPARATE folder (<out-dir>_expected) so it never mixes with input data.

A fixed --seed makes every run reproducible.
"""
import argparse
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
BASE_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)
COUNTRIES = ["IN", "US", "GB", "DE", "FR", "SG", "AU"]
CATEGORIES = ["electronics", "books", "home", "toys", "sports", "grocery"]
STATUSES = ["placed", "shipped", "cancelled", "returned"]
FIRST_NAMES = ["Asha", "Ravi", "Meera", "John", "Sara", "Liam", "Noor", "Chen", "Ana", "Omar"]
LAST_NAMES = ["Sharma", "Khan", "Smith", "Garcia", "Muller", "Singh", "Brown", "Lee", "Rossi", "Das"]

# Column positions, used by the bad-record mutations below
CUSTOMER_HEADER = ["customer_id", "full_name", "email", "country", "updated_at"]
PRODUCT_HEADER = ["product_id", "product_name", "category", "list_price", "updated_at"]
ORDER_HEADER = ["order_id", "customer_id", "product_id", "quantity", "unit_price",
                "order_status", "order_ts", "updated_at"]


def iso(dt):
    return dt.strftime(TS_FORMAT)


def parse(ts):
    return datetime.strptime(ts, TS_FORMAT).replace(tzinfo=timezone.utc)


def random_ts(rng):
    return BASE_TS + timedelta(seconds=rng.randint(0, 270 * 24 * 3600))


def inject_bad(rng, entries, rate, mutations, updated_idx):
    """Turn a share of the rows into deliberately bad records.

    entries: list of [row, record_key, expected_reject_reason_or_None]
    mutations: {reason: function(row) -> bad row}; "duplicate_key" is handled here.
    """
    n_bad = int(len(entries) * rate)
    for idx in rng.sample(range(len(entries)), n_bad):
        row, key, _ = entries[idx]
        reason = rng.choice(list(mutations))
        if reason == "duplicate_key":
            # A newer copy of the same key arrives; the OLDER one is the expected reject.
            newer = list(row)
            newer[updated_idx] = iso(parse(row[updated_idx]) + timedelta(days=1))
            entries[idx][2] = "duplicate_key"
            entries.append([newer, key, None])
        else:
            entries[idx][0] = mutations[reason](list(row))
            entries[idx][2] = reason
    return entries


def build_customers(rng, n, bad_rate):
    entries = []
    for i in range(1, n + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        row = [f"C{i:06d}", f"{first} {last}", f"{first.lower()}.{last.lower()}{i}@example.com",
               rng.choice(COUNTRIES), iso(random_ts(rng))]
        entries.append([row, row[0], None])
    mutations = {
        "missing_required_field": lambda r: [r[0], ""] + r[2:],
        "invalid_email": lambda r: r[:2] + ["not-an-email"] + r[3:],
        "malformed_row": lambda r: r[:3],
        "duplicate_key": None,
    }
    return inject_bad(rng, entries, bad_rate, mutations, updated_idx=4)


def build_products(rng, n, bad_rate):
    entries = []
    for i in range(1, n + 1):
        row = [f"P{i:05d}", f"Product {i}", rng.choice(CATEGORIES),
               f"{rng.uniform(5, 500):.2f}", iso(random_ts(rng))]
        entries.append([row, row[0], None])
    mutations = {
        "missing_required_field": lambda r: [r[0], ""] + r[2:],
        "invalid_price": lambda r: r[:3] + ["-5.00"] + r[4:],
        "malformed_row": lambda r: r[:3],
        "duplicate_key": None,
    }
    return inject_bad(rng, entries, bad_rate, mutations, updated_idx=4)


def build_orders(rng, n, bad_rate, good_customers, good_products):
    entries = []
    for i in range(1, n + 1):
        product_id, price = rng.choice(good_products)
        ts = iso(random_ts(rng))
        row = [f"O{i:08d}", rng.choice(good_customers), product_id, str(rng.randint(1, 10)),
               price, rng.choice(STATUSES), ts, ts]
        entries.append([row, row[0], None])
    mutations = {
        "missing_required_field": lambda r: [r[0], ""] + r[2:],
        "invalid_customer_ref": lambda r: [r[0], "C999999"] + r[2:],
        "invalid_product_ref": lambda r: r[:2] + ["P99999"] + r[3:],
        "invalid_quantity": lambda r: r[:3] + ["0"] + r[4:],
        "invalid_price": lambda r: r[:4] + ["-1.00"] + r[5:],
        "invalid_status": lambda r: r[:5] + ["pending_review"] + r[6:],
        "future_order_ts": lambda r: r[:6] + ["2099-01-01T00:00:00Z"] + r[7:],
        "malformed_row": lambda r: r[:5],
        "duplicate_key": None,
    }
    return inject_bad(rng, entries, bad_rate, mutations, updated_idx=7)


def write_file(rng, out_dir, name, header, entries, expected):
    """Shuffle (gives out-of-order data), write the CSV, record the answer key."""
    rng.shuffle(entries)
    with open(out_dir / name, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        for row_number, (row, key, reason) in enumerate(entries, start=1):
            writer.writerow(row)
            if reason:
                expected.append([name, row_number, key, reason])
    return len(entries)


def main():
    p = argparse.ArgumentParser(description="Generate synthetic order data")
    p.add_argument("--out-dir", default="data/sample")
    p.add_argument("--customers", type=int, default=100)
    p.add_argument("--products", type=int, default=30)
    p.add_argument("--orders", type=int, default=300)
    p.add_argument("--bad-rate", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    rng = random.Random(args.seed)
    out_dir = Path(args.out_dir)
    expected_dir = out_dir.parent / (out_dir.name + "_expected")
    out_dir.mkdir(parents=True, exist_ok=True)
    expected_dir.mkdir(parents=True, exist_ok=True)

    customers = build_customers(rng, args.customers, args.bad_rate)
    products = build_products(rng, args.products, args.bad_rate)
    # Orders only reference customers/products that will be valid, so every
    # expected reject is exactly the one we injected.
    good_customers = [e[1] for e in customers if e[2] in (None, "duplicate_key")]
    good_products = [(e[0][0], e[0][3]) for e in products if e[2] is None]
    orders = build_orders(rng, args.orders, args.bad_rate, good_customers, good_products)

    expected = []
    counts = {
        "customers.csv": write_file(rng, out_dir, "customers.csv", CUSTOMER_HEADER, customers, expected),
        "products.csv": write_file(rng, out_dir, "products.csv", PRODUCT_HEADER, products, expected),
        "orders.csv": write_file(rng, out_dir, "orders.csv", ORDER_HEADER, orders, expected),
    }

    with open(expected_dir / "expected_rejects.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["source_file", "source_row_number", "record_key", "expected_reason"])
        writer.writerows(expected)

    print(f"Seed {args.seed}. Rows written: {counts}")
    print(f"Deliberately bad rows: {len(expected)} (answer key in {expected_dir})")


if __name__ == "__main__":
    main()