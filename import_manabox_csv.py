#!/usr/bin/env python3
"""Import ManaBox CSV data into SQL Server."""

import argparse
import csv
from decimal import Decimal, InvalidOperation
# `pyodbc` is only required when actually inserting into the database.
try:
    import pyodbc  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - allows dry-run without driver
    pyodbc = None

# Connection details
CONN_STR = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=projectmaster,8089;"
    "DATABASE=MTG;"
    "UID=SA;"
    "PWD=R9DL337kY^QC^MBbel7j;"
    "TrustServerCertificate=yes;"
)

INSERT_SQL = (
    """
    INSERT INTO dbo.Cards
        (Name, SetCode, SetName, CollectorNumber, Foil, Rarity, ManaBoxID,
         ScryfallID, PurchasePrice, Misprint, Altered, Condition, Language,
         PurchasePriceCurrency, Location, CardType, DoubleSided)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
)


def parse_bool(value: str) -> int:
    return 1 if str(value).strip().lower() == "true" else 0


def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return Decimal("0")


def read_rows(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            qty = parse_int(row.get("Quantity", 1)) or 1
            for _ in range(qty):
                yield (
                    row.get("Name"),
                    row.get("Set code"),
                    row.get("Set name"),
                    parse_int(row.get("Collector number")),
                    row.get("Foil", "normal"),
                    row.get("Rarity"),
                    parse_int(row.get("ManaBox ID")),
                    row.get("Scryfall ID"),
                    parse_decimal(row.get("Purchase price")),
                    parse_bool(row.get("Misprint", "false")),
                    parse_bool(row.get("Altered", "false")),
                    row.get("Condition", "near_mint"),
                    row.get("Language", "en"),
                    row.get("Purchase price currency", "USD"),
                    "Bulk",
                    "Origional",
                    1 if "//" in (row.get("Name") or "") else 0,
                )


def main(path: str, dry_run: bool = False) -> None:
    rows = list(read_rows(path))
    if dry_run:
        print(f"Prepared {len(rows)} rows")
        return

    if pyodbc is None:
        raise ImportError("pyodbc is required for database insertion")

    with pyodbc.connect(CONN_STR) as conn:
        cursor = conn.cursor()
        cursor.fast_executemany = True
        cursor.executemany(INSERT_SQL, rows)
        conn.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import ManaBox CSV into SQL Server")
    parser.add_argument("csv_file", help="Path to ManaBox CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Parse file but do not insert")
    args = parser.parse_args()
    main(args.csv_file, args.dry_run)
