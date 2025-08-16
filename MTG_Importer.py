#!/usr/bin/env python3
"""Import ManaBox CSV data into SQL Server."""

import argparse
import csv
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Tuple, Set
from urllib.error import URLError, HTTPError
from urllib.parse import quote
from urllib.request import urlopen

# `pyodbc` is only required when actually inserting into the database.
try:
    import pyodbc  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - allows dry-run without driver
    pyodbc = None


def build_conn_str(server: str, database: str, user: str, password: str) -> str:
    """Choose an available SQL Server ODBC driver and build a connection string."""

    if pyodbc is None:
        raise ImportError("pyodbc is required for database insertion")

    # Look for any installed Microsoft ODBC driver for SQL Server, preferring the latest.
    drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
    if not drivers:
        raise RuntimeError(
            "No suitable ODBC SQL Server driver found. Install 'ODBC Driver 17 for SQL Server' or newer."
        )
    driver = sorted(drivers)[-1]

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )

INSERT_SQL = (
    """
    INSERT INTO dbo.Cards
        (Name, SetCode, SetName, CollectorNumber, Foil, Rarity, Legendary, ManaBoxID,
         ScryfallID, PurchasePrice, Misprint, Altered, Condition, Language,
         PurchasePriceCurrency, Location, CardType, DoubleSided, CreatedDate)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


_legendary_cache: Dict[Tuple[Optional[str], Optional[str], Optional[str]], Optional[int]] = {}


def fetch_legendary(
    scryfall_id: Optional[str], name: Optional[str], set_code: Optional[str]
) -> Optional[int]:
    """Return 1 if the card is legendary, 0 if not, or None if unknown."""

    key = (scryfall_id, name, set_code)
    if key in _legendary_cache:
        return _legendary_cache[key]

    try:
        if scryfall_id:
            url = f"https://api.scryfall.com/cards/{scryfall_id}"
        else:
            if not name:
                return None
            qname = quote(name)
            url = f"https://api.scryfall.com/cards/named?exact={qname}"
            if set_code:
                url += f"&set={quote(set_code)}"
        with urlopen(url) as resp:
            data = json.load(resp)
    except (URLError, HTTPError, json.JSONDecodeError):
        result = None
    else:
        type_line = data.get("type_line", "")
        result = 1 if "Legendary" in type_line else 0

    _legendary_cache[key] = result
    return result


def read_rows(
    csv_path: str,
    location: str = "Bulk",
    card_type: str = "Original",
    purchase_price_override: Optional[Decimal] = None,
):
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            qty = parse_int(row.get("Quantity", 1)) or 1
            legendary = fetch_legendary(
                row.get("Scryfall ID"), row.get("Name"), row.get("Set code")
            )
            for _ in range(qty):
                purchase_price = (
                    parse_decimal(row.get("Purchase price"))
                    if purchase_price_override is None
                    else purchase_price_override
                )
                yield (
                    row.get("Name"),
                    row.get("Set code"),
                    row.get("Set name"),
                    parse_int(row.get("Collector number")),
                    row.get("Foil", "normal"),
                    row.get("Rarity"),
                    legendary,
                    parse_int(row.get("ManaBox ID")),
                    row.get("Scryfall ID"),
                    purchase_price,
                    parse_bool(row.get("Misprint", "false")),
                    parse_bool(row.get("Altered", "false")),
                    row.get("Condition", "near_mint"),
                    row.get("Language", "en"),
                    row.get("Purchase price currency", "USD"),
                    location,
                    card_type,
                    1 if "//" in (row.get("Name") or "") else 0,
                    datetime.now(),
                )


def import_csv(
    path: str,
    dry_run: bool = False,
    server: Optional[str] = None,
    database: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    location: str = "Bulk",
    card_type: str = "Original",
    purchase_price_override: Optional[Decimal] = None,
) -> None:
    rows = list(read_rows(path, location, card_type, purchase_price_override))
    if dry_run:
        print(f"Prepared {len(rows)} rows")
        return

    if pyodbc is None:
        raise ImportError("pyodbc is required for database insertion")

    if None in {server, database, user, password}:
        raise ValueError("Database connection details are required unless --dry-run is used")

    conn_str = build_conn_str(server, database, user, password)
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        cursor.fast_executemany = True
        cursor.executemany(INSERT_SQL, rows)
        conn.commit()


def populate_legendary(
    server: str,
    database: str,
    user: str,
    password: str,
) -> None:
    """Populate the Legendary column for existing cards lacking a value."""

    if pyodbc is None:
        raise ImportError("pyodbc is required for database insertion")

    conn_str = build_conn_str(server, database, user, password)
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, ScryfallID, Name, SetCode FROM dbo.Cards WHERE Legendary IS NULL"
        )
        rows = cursor.fetchall()
        for card_id, scryfall_id, name, set_code in rows:
            legendary = fetch_legendary(scryfall_id, name, set_code)
            if legendary is not None:
                cursor.execute(
                    "UPDATE dbo.Cards SET Legendary = ? WHERE id = ?",
                    legendary,
                    card_id,
                )
        conn.commit()


def compare_cards(
    text_file: str,
    location: str,
    server: str,
    databasetable: str,
    user: str,
    password: str,
) -> None:
    """Compare card names from a text file and the database."""

    if pyodbc is None:
        raise ImportError("pyodbc is required for database access")

    parts = databasetable.split(".")
    if len(parts) < 2:
        raise ValueError("databasetable must be in the form Database.Schema.Table")
    database = parts[0]
    table = ".".join(parts[1:])

    names_in_file: Set[str] = set()
    with open(text_file, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("//"):
                if line.startswith("// MAYBEBOARD"):
                    break
                continue
            if not line:
                continue
            try:
                _, remainder = line.split(" ", 1)
            except ValueError:
                continue
            name = remainder.split("(")[0].strip()
            if name:
                names_in_file.add(name)

    conn_str = build_conn_str(server, database, user, password)
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT Name FROM {table} WHERE Location = ? AND CardType <> 'Backer'",
            location,
        )
        names_in_db = {row[0] for row in cursor.fetchall()}

    db_only = sorted(names_in_db - names_in_file)
    file_only = sorted(names_in_file - names_in_db)
    both = sorted(names_in_file & names_in_db)

    print("Cards in database but not in file:")
    for name in db_only:
        print(name)

    print("\nCards in file but not in database:")
    for name in file_only:
        print(name)

    print("\nCards in both:")
    for name in both:
        print(name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tools for MTG card imports")
    subparsers = parser.add_subparsers(dest="command", required=True)

    imp_parser = subparsers.add_parser("import", help="Import ManaBox CSV into SQL Server")
    imp_parser.add_argument("csv_file", help="Path to ManaBox CSV file")
    imp_parser.add_argument("--dry-run", action="store_true", help="Parse file but do not insert")
    imp_parser.add_argument("--server", help="SQL Server host[,port]")
    imp_parser.add_argument("--database", default="MTG", help="Database name")
    imp_parser.add_argument("--user", help="Database user")
    imp_parser.add_argument("--password", help="Database password")
    imp_parser.add_argument("--location", default="Bulk", help="Location to store cards")
    imp_parser.add_argument(
        "--cardtype", default="Original", help="Value for CardType column"
    )
    imp_parser.add_argument(
        "--setpurchaseprice",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use purchase price from CSV (disable with --no-setpurchaseprice)",
    )

    leg_parser = subparsers.add_parser(
        "populate-legendary", help="Populate Legendary column for existing cards"
    )
    leg_parser.add_argument("--server", required=True, help="SQL Server host[,port]")
    leg_parser.add_argument("--database", default="MTG", help="Database name")
    leg_parser.add_argument("--user", required=True, help="Database user")
    leg_parser.add_argument("--password", required=True, help="Database password")

    cmp_parser = subparsers.add_parser(
        "compare", help="Compare card names in a text file with the database"
    )
    cmp_parser.add_argument("text_file", help="Path to text file")
    cmp_parser.add_argument("--location", required=True, help="Location value to query")
    cmp_parser.add_argument("--server", required=True, help="SQL Server host[,port]")
    cmp_parser.add_argument(
        "--databasetable",
        default="MTG.dbo.Cards",
        help="Database and table in the form Database.Schema.Table",
    )
    cmp_parser.add_argument("--user", required=True, help="Database user")
    cmp_parser.add_argument("--password", required=True, help="Database password")

    args = parser.parse_args()

    if args.command == "import":
        if not args.dry_run:
            missing = [name for name in ("server", "user", "password") if getattr(args, name) is None]
            if missing:
                imp_parser.error(
                    "--server, --user, and --password are required unless --dry-run is specified"
                )
        import_csv(
            args.csv_file,
            args.dry_run,
            args.server,
            args.database,
            args.user,
            args.password,
            location=args.location,
            card_type=args.cardtype,
            purchase_price_override=(
                None if args.setpurchaseprice else Decimal("0")
            ),
        )
    elif args.command == "populate-legendary":
        populate_legendary(args.server, args.database, args.user, args.password)
    elif args.command == "compare":
        compare_cards(
            args.text_file,
            args.location,
            args.server,
            args.databasetable,
            args.user,
            args.password,
        )
