"""
Auto-sync runner: scan data/ for bank CSVs, route to the correct account, upload,
then move processed files into data/processed/.

Usage:
  uv run python -m src.auto_sync

Routing rules:
  - Preferred: add `file_prefixes` list under each account in config/accounts.yml.
    A file whose name contains any of those strings will be routed to that account.
  - Fallback heuristics (Lloyds example):
    * If filename contains "50038063" and an account named 'lloyds_cash' exists, route to it.
    * If filename contains "4205" and an account named 'lloyds_credit' exists, route to it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import shutil
from datetime import datetime

from src.utils.logger import logger
from src.banks.lloyds import parse_lloyds_csv
from src.sheets import fetch_existing_rows, append_rows
from src.sheets import sort_worksheet
from src.fina_writer import write_fina_csv
from collections import Counter

from src.personal_sync import _load_settings, Settings, AccountCfg


DATA_DIR = Path("data")
PROCESSED_DIR = DATA_DIR / "processed"


def _account_prefixes_map(settings: Settings) -> Dict[str, List[str]]:
    """Return a map of account.name -> file_prefixes (may be empty)."""
    prefixes: Dict[str, List[str]] = {}
    # file_prefixes may be set in YAML under each account; it's not part of AccountCfg dataclass,
    # so we can't read it directly from the object. We will attempt to re-open the YAML lazily.
    # To keep it simple and robust, we'll rely on filename heuristics here and use known defaults.
    # If you want strict config-driven routing, add file_prefixes to your YAML and extend the loader.
    for acc in settings.accounts:
        prefixes[acc.name] = []
    # Known convenient defaults (based on user context)
    names = {a.name for a in settings.accounts}
    if "lloyds_cash" in names:
        prefixes["lloyds_cash"].extend(["50038063"])  # cash account number
    if "lloyds_credit" in names:
        prefixes["lloyds_credit"].extend(["4205"])  # credit card tail/prefix
    return prefixes


def _route_file_to_account(filename: str, settings: Settings) -> Optional[AccountCfg]:
    mapping = _account_prefixes_map(settings)
    for acc in settings.accounts:
        for pref in mapping.get(acc.name, []):
            if pref and pref in filename:
                return acc
    return None


def _base_key(rec: dict) -> Tuple[str, str, str, str]:
    return (
        rec.get("Date", ""),
        rec.get("Amount", ""),
        rec.get("Name", ""),
        rec.get("Merchant", ""),
    )


def _process_file_for_account(csv_path: Path, settings: Settings, acct: AccountCfg) -> Tuple[int, int]:
    """Parse, dedupe vs sheet, append. Returns (appended, skipped_existing)."""
    bank = acct.bank.lower()
    currency = acct.currency
    worksheet = acct.worksheet

    if bank != "lloyds":
        raise SystemExit(f"Unsupported bank: {bank}")

    rows_list = list(parse_lloyds_csv(str(csv_path), currency=currency))

    # Determine sheet id target
    target_sheet_id = acct.sheet_id or settings.sheet_id
    if not target_sheet_id:
        raise SystemExit(
            f"No sheet_id configured for account '{acct.name}'. Set account.sheet_id or default_sheet_id in config/accounts.yml"
        )

    existing = fetch_existing_rows(
        sheet_id=target_sheet_id,
        worksheet_name=worksheet,
        json_keyfile_path=settings.service_account_keyfile,
    )

    src_counter = Counter(_base_key(r) for r in rows_list)
    existing_counter = Counter(_base_key(r) for r in existing)
    allowance = {k: max(0, src_counter[k] - existing_counter[k]) for k in src_counter}

    to_upload: List[Dict[str, str]] = []
    mode = getattr(acct, "dedupe_mode", getattr(acct, "dedupe", "frequency"))
    threshold = getattr(acct, "dedupe_threshold", getattr(acct, "small_amount_threshold", None))
    if mode == "strict":
        seen = set(_base_key(r) for r in existing)
        for r in rows_list:
            k = _base_key(r)
            if k in seen:
                continue
            seen.add(k)
            to_upload.append(r)
    elif mode in ("hybrid", "smart") and threshold is not None:
        thr = float(threshold)
        seen = set(_base_key(r) for r in existing)
        def _amt(rec: dict) -> float:
            try:
                return float(str(rec.get("Amount", "0")).replace(",", ""))
            except Exception:
                return 0.0
        for r in rows_list:
            k = _base_key(r)
            if abs(_amt(r)) <= thr:
                if allowance.get(k, 0) > 0:
                    to_upload.append(r)
                    allowance[k] -= 1
            else:
                if k not in seen:
                    to_upload.append(r)
                    seen.add(k)
    else:
        for r in rows_list:
            k = _base_key(r)
            if allowance.get(k, 0) > 0:
                to_upload.append(r)
                allowance[k] -= 1

    appended = append_rows(
        sheet_id=target_sheet_id,
        worksheet_name=worksheet,
        rows=to_upload,
        json_keyfile_path=settings.service_account_keyfile,
    )
    skipped = len(rows_list) - appended
    logger.info(
        f"auto_sync.append account={acct.name} worksheet='{worksheet}' file='{csv_path.name}' appended={appended} skipped_existing={skipped}"
    )

    # Optional local CSV output controlled by settings.write_local_csv
    if settings.write_local_csv:
        out_csv = csv_path.with_suffix("")
        out_csv = Path(f"{out_csv}_fina.csv")
        write_fina_csv(rows_list, str(out_csv))
        logger.info(f"auto_sync.wrote_local {out_csv}")

    # Optional post-append sort via Sheets API
    if appended > 0 and getattr(acct, "sort_column", None):
        sort_worksheet(
            sheet_id=target_sheet_id,
            worksheet_name=worksheet,
            sort_by=getattr(acct, "sort_column"),
            ascending=bool(getattr(acct, "sort_ascending", False)),
            json_keyfile_path=settings.service_account_keyfile,
        )

    return appended, skipped


def _move_to_processed(csv_path: Path) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dest = PROCESSED_DIR / csv_path.name
    if dest.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = PROCESSED_DIR / f"{csv_path.stem}_{ts}{csv_path.suffix}"
    shutil.move(str(csv_path), str(dest))
    logger.info(f"auto_sync.moved file='{csv_path.name}' -> '{dest}'")
    return dest


def _service_account_email(keyfile_path: str) -> Optional[str]:
    try:
        import json
        with open(keyfile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("client_email")
    except Exception:
        return None


def _preflight_access(settings: Settings) -> List[str]:
    """Check spreadsheet access for each account. Return list of account names to skip."""
    blocked: List[str] = []
    for acct in settings.accounts:
        target_sheet_id = acct.sheet_id or settings.sheet_id
        if not target_sheet_id:
            logger.error(
                f"auto_sync.preflight_missing_sheet_id account={acct.name} — set account.sheet_id in config/accounts.yml"
            )
            blocked.append(acct.name)
            continue
        try:
            # Retry a few times for transient API errors (e.g., 5xx)
            import time
            attempts = 3
            delay = 1.0
            last_exc: Optional[Exception] = None
            for _ in range(attempts):
                try:
                    _ = fetch_existing_rows(
                        sheet_id=target_sheet_id,
                        worksheet_name=acct.worksheet,
                        json_keyfile_path=settings.service_account_keyfile,
                    )
                    last_exc = None
                    break
                except Exception as ee:
                    last_exc = ee
                    time.sleep(delay)
                    delay *= 2
            if last_exc:
                raise last_exc
            logger.debug(
                f"auto_sync.preflight_ok account={acct.name} sheet_id={target_sheet_id} worksheet='{acct.worksheet}'"
            )
        except Exception as e:
            try:
                from gspread.exceptions import SpreadsheetNotFound  # type: ignore
            except Exception:
                SpreadsheetNotFound = None  # type: ignore
            if SpreadsheetNotFound and isinstance(e, SpreadsheetNotFound):  # type: ignore
                sa_email = _service_account_email(settings.service_account_keyfile) or "<service-account-email>"
                logger.error(
                    (
                        f"auto_sync.preflight_no_access account={acct.name} sheet_id={target_sheet_id} — "
                        f"Spreadsheet not found or not shared. Share the sheet with '{sa_email}' (Editor), "
                        f"or verify the sheet ID. Skipping this account."
                    )
                )
                blocked.append(acct.name)
            else:
                logger.exception(
                    f"auto_sync.preflight_error account={acct.name} sheet_id={target_sheet_id} err={e}"
                )
                blocked.append(acct.name)
    return blocked


def main():
    settings = _load_settings()
    if not settings.accounts:
        logger.warning("No accounts configured; nothing to do.")
        return

    if not DATA_DIR.exists():
        logger.warning(f"Data directory not found: {DATA_DIR}")
        return

    # Preflight: ensure we can access each account's spreadsheet
    blocked_accounts = set(_preflight_access(settings))

    files = sorted([p for p in DATA_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".csv"])
    if not files:
        logger.info("auto_sync.no_files data directory is empty")
        return

    for f in files:
        acct = _route_file_to_account(f.name, settings)
        if not acct:
            logger.warning(f"auto_sync.unmatched file='{f.name}'; no route found. Skipping.")
            continue
        if acct.name in blocked_accounts:
            logger.warning(
                f"auto_sync.skip_blocked file='{f.name}' account={acct.name} due to failed preflight access"
            )
            continue
        try:
            _process_file_for_account(f, settings, acct)
            _move_to_processed(f)
        except Exception as e:
            logger.exception(f"auto_sync.error file='{f.name}' err={e}")


if __name__ == "__main__":
    main()
