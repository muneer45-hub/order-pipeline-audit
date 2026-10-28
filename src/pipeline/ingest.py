"""Reading input files: checksum, header (schema) check, row numbering."""
import csv
import hashlib


class SchemaError(Exception):
    """The file's header is missing or does not match the expected columns."""


def file_checksum(path):
    """SHA-256 of the file bytes. Identifies a file so reruns can be detected."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path, expected_columns):
    """Return [(source_row_number, values), ...]; row numbers start at 1 after the header.

    Raises SchemaError if the file is empty or the header differs from expected.
    A header-only file is a valid empty batch and returns [].
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise SchemaError("file is empty: no header row")
        header = [h.strip() for h in header]
        if header != expected_columns:
            raise SchemaError(f"unexpected header {header}; expected {expected_columns}")
        return [(number, row) for number, row in enumerate(reader, start=1)]