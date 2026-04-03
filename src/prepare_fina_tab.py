"""
Prepare a single 'Transactions' tab for Fina by combining cash and credit tabs.

Usage:
  uv run python -m src.prepare_fina_tab

It will:
  - Read rows from the configured cash and credit worksheets
  - Dedupe by the normalized Fina fingerprint
  - Create or clear a 'Transactions' tab
  - Write the Fina header and all combined rows
"""

from typing import List, Dict
from collections import OrderedDict

from src import personal_sync as ps
from src.fina_writer import FIELDNAMES
from src.sheets import fetch_existing_rows
from src.dedupe import txn_fingerprint
from src.utils.logger import logger

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception as e:
    gspread = None
    Credentials = None


def _client_from_service_account(json_keyfile_path: str):
    if Credentials is None or gspread is None:
        raise RuntimeError("Google libraries not installed. Please install gspread and google-auth.")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(json_keyfile_path, scopes=scopes)
    return gspread.authorize(creds)


def _combined_rows() -> List[Dict[str, str]]:
    # Load settings via personal_sync to avoid duplication
    settings = ps._load_settings()
    # Find accounts for cash and credit by name (convention), fallback to defaults
    cash_acc = next((a for a in settings.accounts if a.name == "lloyds_cash"), None)
    credit_acc = next((a for a in settings.accounts if a.name == "lloyds_credit"), None)
    cash_ws = cash_acc.worksheet if cash_acc else "ClubLloyds (cash)"
    credit_ws = credit_acc.worksheet if credit_acc else "LloydsCredit (credit)"

    # Determine sheet_id to read from: prefer account-level override, else global default
    cash_sheet_id = (cash_acc.sheet_id if cash_acc and cash_acc.sheet_id else settings.sheet_id)
    credit_sheet_id = (credit_acc.sheet_id if credit_acc and credit_acc.sheet_id else settings.sheet_id)
    if not cash_sheet_id or not credit_sheet_id:
        raise SystemExit("prepare_fina_tab: sheet_id not configured. Set default_sheet_id or per-account sheet_id in config/accounts.yml")

    cash = fetch_existing_rows(cash_sheet_id, cash_ws, settings.service_account_keyfile)
    credit = fetch_existing_rows(credit_sheet_id, credit_ws, settings.service_account_keyfile)
    logger.info(f"prepare_fina_tab source counts cash={len(cash)} credit={len(credit)}")

    all_rows = cash + credit

    # Dedupe by fingerprint while preserving order
    seen = set()
    deduped: List[Dict[str, str]] = []
    for r in all_rows:
        fp = txn_fingerprint(r)
        if fp in seen:
            continue
        seen.add(fp)
        # normalize to FIELDNAMES order
        deduped.append({k: r.get(k, "") for k in FIELDNAMES})

    # Sort by Date ascending, then Amount as secondary for determinism
    deduped.sort(key=lambda r: (r.get("Date", ""), r.get("Amount", "")))
    return deduped


def main():
    logger.info("prepare_fina_tab start")
    client = _client_from_service_account(ps.SERVICE_ACCOUNT_KEYFILE)
    sh = client.open_by_key(ps.SHEET_ID)

    # Create or clear 'Transactions' tab
    ws_title = "Transactions"
    try:
        ws = sh.worksheet(ws_title)
        ws.clear()
        logger.info("prepare_fina_tab cleared existing Transactions tab")
    except Exception:
        ws = sh.add_worksheet(title=ws_title, rows=1000, cols=len(FIELDNAMES))
        logger.info("prepare_fina_tab created Transactions tab")

    # Write header
    ws.update('1:1', [FIELDNAMES])

    rows = _combined_rows()
    if not rows:
        logger.info("prepare_fina_tab no rows to write")
        return

    # Chunked append
    out_rows = [[r.get(h, "") for h in FIELDNAMES] for r in rows]
    CHUNK = 200
    total = 0
    for i in range(0, len(out_rows), CHUNK):
        ws.append_rows(out_rows[i:i+CHUNK], value_input_option="USER_ENTERED")
        total += len(out_rows[i:i+CHUNK])
    logger.info(f"prepare_fina_tab wrote rows={total}")


if __name__ == "__main__":
    main()
