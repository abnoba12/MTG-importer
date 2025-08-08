# MTG-importer

A simple script to import ManaBox CSV exports into the `MTG` SQL Server database.

## Setup

1. Install Python 3.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Export your collection from ManaBox as a CSV file.
2. Run the importer:
   ```bash
   python import_manabox_csv.py <path-to-csv>
   ```
   Use `--dry-run` to see how many rows would be inserted without touching the database.

Connection details are configured inside `import_manabox_csv.py`. The script assumes
all cards should be stored in location `Bulk`, type `Origional`, and marks cards with
"//" in their name as double sided.
