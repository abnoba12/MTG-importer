# MTG-importer

A simple script to import ManaBox CSV exports into the `MTG` SQL Server database.
It also offers a helper command to backfill card metadata from the Scryfall API.

## Setup

1. Install Python 3.
2. Install a Microsoft ODBC driver for SQL Server (version 17 or newer). On
   Windows the installer is available at
   [learn.microsoft.com](https://learn.microsoft.com/sql/connect/odbc/).
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Export your collection from ManaBox as a CSV file.
2. Import the CSV:
   ```bash
   python import_manabox_csv.py import <path-to-csv> --server <host[,port]> \
       --database MTG --user <username> --password <password>
   ```
   Use `--dry-run` to see how many rows would be prepared without touching the database.
   During import, the script queries the [Scryfall API](https://scryfall.com/docs/api)
   to determine whether each card is legendary.
3. To backfill the `Legendary` flag for cards already in the database:
   ```bash
   python import_manabox_csv.py populate-legendary --server <host[,port]> \
       --database MTG --user <username> --password <password>
   ```

The script automatically selects an installed SQL Server ODBC driver. It assumes all
cards should be stored in location `Bulk`, type `Origional`, and marks cards with "//"
in their name as double sided. If the Scryfall API cannot be reached, the `Legendary`
column is left null.
