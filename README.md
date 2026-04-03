fina-converter
==============

Simple workflow to convert bank CSV exports (Lloyds) to Fina format and append to Google Sheets with dedupe and auto-sort.

Quick start
-----------
1) Download your latest CSV(s) from your bank.
2) Drop them into `data/` (we’ll move processed files into `data/processed/`).
3) Configure `config/accounts.yml` per account:
   - `sheet_id`: Spreadsheet ID for that account
   - `worksheet`: Tab name to append to (will be created with the Fina header if missing)
   - `file_prefixes`: Routing hints (e.g., `50038063` for cash, `4205` for credit)
   - `sort`: Optional auto-sort, e.g. `{ column: "Date", ascending: false }`
   - `google.service_account_keyfile`: Path to your JSON key (default `credentials/service_account.json`)
4) Share each spreadsheet with your service account email (Editor).
5) Run:
   ```zsh
   uv run python -m src.auto_sync
   ```

What happens
------------
- Parses Lloyds CSVs into the Fina schema: `Date, Amount, Name, Merchant, txn_id, Category, Currency, City, Region`
- Generates a stable `txn_id` during parsing and dedupes against Sheets using that id when available
- Appends only new rows, initializes header if absent, then auto-sorts by your config
- Moves each processed file into `data/processed/`

Setup (one-time)
----------------
- Python 3.10+ and uv
- Install deps:
  ```zsh
  uv sync
  ```
- Google service account:
  - Save the JSON key to `credentials/service_account.json`
  - Share each target spreadsheet with the service account email (Editor)

Notes
-----
- Fina reads the FIRST worksheet in a spreadsheet. Keep one spreadsheet per account, or ensure the tab Fina should read is first.
- Tabs are created on-demand and the Fina header is set automatically.
- Preflight access checks run at startup and will tell you if a spreadsheet isn’t shared or the ID is wrong.

Optional tools
--------------
- Manual per-account sync: `uv run python -m src.personal_sync` (uses the same config)
- Prepare combined `Transactions` tab: `uv run python -m src.prepare_fina_tab` (optional)
- Archived backfills (guarded):
  - Cash: `uv run python -m src.archive.oneoff_import_prev --archive`
  - Credit: `uv run python -m src.archive.oneoff_import_credit_prev --archive`

Troubleshooting
---------------
- Sheet doesn’t update:
  - Check preflight logs for access errors (share with the service account)
  - Confirm `sheet_id` and `worksheet` names match your Sheet
- Sorting:
  - Enable in `config/accounts.yml` with `sort: { column: "Date", ascending: false }`
  - Dates must be real dates in Sheets (Format > Number > Date)
- Duplicates:
  - We dedupe by `txn_id` for newly imported rows, with a compatibility fallback for older sheet rows that predate the `txn_id` column

See also (Obsidian)
-------------------
- Quick guide: `docs/obsidian/guide.md`
- Simple architecture: `docs/obsidian/architecture.md`
