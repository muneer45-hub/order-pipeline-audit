"""The validator must flag exactly the rows the generator deliberately broke.

The answer key lives in data/sample_expected, separate from the input data.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import ENTITIES
from pipeline.ingest import read_csv
from pipeline.validate import validate_batch

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "data" / "sample"
KEY_FILE = ROOT / "data" / "sample_expected" / "expected_rejects.csv"
NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)


def load_expected():
    with open(KEY_FILE, newline="", encoding="utf-8") as f:
        return {(r["source_file"], int(r["source_row_number"]), r["expected_reason"])
                for r in csv.DictReader(f)}


def test_validation_matches_answer_key():
    refs, actual = {}, set()
    for entity, spec in ENTITIES.items():
        rows = read_csv(SAMPLE_DIR / spec["file"], spec["columns"])
        accepted, rejected = validate_batch(entity, rows, NOW, refs)
        # every input row is either accepted or rejected, never lost
        assert len(accepted) + len(rejected) == len(rows)
        actual |= {(spec["file"], r.row_number, r.reason) for r in rejected}
        refs[spec["key"]] = {record[spec["key"]] for _, record in accepted}

    expected = load_expected()
    assert actual - expected == set(), "pipeline rejected rows that were not meant to be bad"
    assert expected - actual == set(), "pipeline missed deliberately bad rows"