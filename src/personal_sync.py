"""
Personal runner for syncing bank CSVs to Google Sheets without CLI args.

Recommended usage:
    uv run python -m src.personal_sync

Configuration:
    - Reads settings from `config/accounts.yml` (preferred)
    - Falls back to the built-in defaults if the YAML is missing

Requirements:
    - `credentials/service_account.json` must exist and the service account
        must have Editor access to the target spreadsheet.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.banks.lloyds import parse_lloyds_csv
from src.fina_writer import write_fina_csv
from src.sheets import append_rows, fetch_existing_rows, sort_worksheet
from src.transaction_identity import filter_upload_rows
from src.utils.logger import logger

try:
    import yaml
except Exception:
    yaml = None


@dataclass
class AccountCfg:
    name: str
    bank: str
    currency: str
    worksheet: str
    inputs: List[str]
    sheet_id: Optional[str] = None  # Optional per-account override
    # Dedupe mode: 'frequency' (default) allows repeated identical rows if present in the source;
    # 'strict' allows at most one per key; 'smart' uses strict for large amounts and frequency for small amounts.
    dedupe: str = "frequency"
    small_amount_threshold: Optional[float] = None
    # Optional post-append sorting
    sort_column: Optional[str] = None
    sort_ascending: bool = False


@dataclass
class Settings:
    service_account_keyfile: str
    sheet_id: Optional[str]  # global default (fallback if account.sheet_id not set)
    write_local_csv: bool
    accounts: List[AccountCfg]


def _load_settings() -> Settings:
    cfg_path = "config/accounts.yml"
    if yaml is None or not os.path.exists(cfg_path):
        # Fallback defaults if YAML missing or PyYAML unavailable
        logger.warning("Using built-in defaults; config/accounts.yml not found or PyYAML missing.")
        return Settings(
            service_account_keyfile="credentials/service_account.json",
            sheet_id=None,
            write_local_csv=False,
            accounts=[],
        )

    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    google = data.get("google", {})
    svc_key = google.get("service_account_keyfile", "credentials/service_account.json")
    # accounts.yml structure: accounts: { name: {bank, currency, sheet_id, worksheet, inputs?, sort?, dedupe?}}
    accounts_map: Dict[str, Dict] = data.get("accounts", {})
    accs: List[AccountCfg] = []
    for name, a in accounts_map.items():
        inputs = a.get("inputs", [])  # allow optional inputs in YAML for convenience
        sort_cfg = a.get("sort") or {}
        if not isinstance(sort_cfg, dict):
            sort_cfg = {}
        # dedupe can be string or mapping
        dedupe_cfg = a.get("dedupe", "frequency")
        dedupe_mode = "frequency"
        small_amount_threshold: Optional[float] = None
        if isinstance(dedupe_cfg, dict):
            dedupe_mode = str(dedupe_cfg.get("mode", "frequency")).lower()
            # accept either 'threshold' or 'small_amount_threshold'
            raw_thr = dedupe_cfg.get("threshold", dedupe_cfg.get("small_amount_threshold"))
            if raw_thr is not None:
                try:
                    small_amount_threshold = float(raw_thr)
                except Exception:
                    small_amount_threshold = None
        else:
            dedupe_mode = str(dedupe_cfg).lower()
        accs.append(
            AccountCfg(
                name=name,
                bank=a.get("bank", "lloyds"),
                currency=a.get("currency", "GBP"),
                worksheet=a.get("worksheet", "Transactions"),
                inputs=inputs,
                sheet_id=a.get("sheet_id"),
                dedupe=dedupe_mode,
                small_amount_threshold=small_amount_threshold,
                sort_column=sort_cfg.get("column"),
                sort_ascending=bool(sort_cfg.get("ascending", False)),
            )
        )
    # Global default sheet_id (not required if set per-account)
    default_sheet_id = data.get("default_sheet_id")
    return Settings(
        service_account_keyfile=svc_key,
        sheet_id=default_sheet_id,
        write_local_csv=bool(data.get("write_local_csv", False)),
        accounts=accs,
    )


def process_account(settings: Settings, acct: AccountCfg):
    bank = acct.bank.lower()
    worksheet = acct.worksheet
    currency = acct.currency
    inputs: List[str] = acct.inputs

    total_appended = 0
    for input_path in inputs:
        p = Path(input_path)
        if not p.exists():
            logger.warning(f"sync.skip_missing account={acct.name} file='{input_path}'")
            continue
        if bank == "lloyds":
            rows_list = list(parse_lloyds_csv(input_path, currency=currency))
        else:
            raise SystemExit(f"Unsupported bank: {bank}")

        if settings.write_local_csv:
            out_csv = Path(input_path).with_suffix("")
            out_csv = Path(f"{out_csv}_fina.csv")
            write_fina_csv(rows_list, str(out_csv))
            logger.info(f"Wrote local CSV {out_csv}")

        # Determine target and fetch existing
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

        to_upload = filter_upload_rows(
            rows_list,
            existing,
            mode=acct.dedupe,
            threshold=acct.small_amount_threshold,
        )

        appended = append_rows(
            sheet_id=target_sheet_id,
            worksheet_name=worksheet,
            rows=to_upload,
            json_keyfile_path=settings.service_account_keyfile,
        )
        total_appended += appended
        skipped = len(rows_list) - appended
        logger.info(
            f"sync.append account={acct.name} worksheet='{worksheet}' file='{input_path}' appended={appended} skipped_existing={skipped}"
        )

        # Optional post-append sort via Sheets API
        if appended > 0 and acct.sort_column:
            sort_worksheet(
                sheet_id=target_sheet_id,
                worksheet_name=worksheet,
                sort_by=acct.sort_column,
                ascending=acct.sort_ascending,
                json_keyfile_path=settings.service_account_keyfile,
            )

    logger.info(f"sync.account_done account={acct.name} total_appended={total_appended}")


def main():
    settings = _load_settings()
    if not settings.accounts:
        logger.warning("No accounts configured. Add accounts to config/accounts.yml under 'accounts:'.")
    for acct in settings.accounts:
        logger.info(f"sync.account_start account={acct.name} worksheet='{acct.worksheet}'")
        process_account(settings, acct)


if __name__ == "__main__":
    main()
