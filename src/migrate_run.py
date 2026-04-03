"""
Helper to migrate historical rows from an old spreadsheet/tab to the new one
you now use for Fina. Edit the variables below and run:

  uv run python -m src.migrate_run

It will copy rows and skip duplicates based on a simple fingerprint.
"""

from typing import List, Dict, Tuple

from src.migrate import migrate_sheet
from src.utils.logger import logger


# --------------- Edit me ---------------
SERVICE_ACCOUNT_KEYFILE = "credentials/service_account.json"

# The old spreadsheet currently linked in Fina (the one you want to unlink)
OLD_SHEET_ID = "PUT_OLD_SHEET_ID_HERE"

# The new spreadsheet you want to keep and link
NEW_SHEET_ID = "PUT_NEW_SHEET_ID_HERE"

# Map of (old_tab -> new_tab) per account
TAB_MAPPINGS = {
    # Example:
    # "Old ClubLloyds": "ClubLloyds (cash)",
    # "Old Lloyds Credit": "LloydsCredit (credit)",
}
# ---------------------------------------


def main():
    if "PUT_OLD_SHEET_ID_HERE" in (OLD_SHEET_ID or "") or "PUT_NEW_SHEET_ID_HERE" in (NEW_SHEET_ID or ""):
        raise SystemExit("Please edit src/migrate_run.py and set OLD_SHEET_ID and NEW_SHEET_ID.")

    total_src = total_skipped = total_appended = 0
    for old_tab, new_tab in TAB_MAPPINGS.items():
        src, skipped, appended = migrate_sheet(
            src_sheet_id=OLD_SHEET_ID,
            src_worksheet=old_tab,
            dst_sheet_id=NEW_SHEET_ID,
            dst_worksheet=new_tab,
            json_keyfile_path=SERVICE_ACCOUNT_KEYFILE,
        )
        total_src += src
        total_skipped += skipped
        total_appended += appended
        logger.info(
            f"Migrated {old_tab} -> {new_tab}: source={src}, skipped(dupes)={skipped}, appended={appended}"
        )

    logger.info(
        f"Totals: source={total_src}, skipped={total_skipped}, appended={total_appended}"
    )


if __name__ == "__main__":
    main()
