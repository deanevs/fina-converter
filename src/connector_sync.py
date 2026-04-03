"""
Connector-based sync runner: fetch transactions from configured providers and append to Google Sheets
with dedupe and optional sorting.

Usage:
  uv run python -m src.connector_sync

Config: see config/connectors.example.yml
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import os

try:
    import yaml
except Exception:
    yaml = None

from src.utils.logger import logger
from src.sheets import fetch_existing_rows, append_rows, sort_worksheet
from src.personal_sync import _load_settings, AccountCfg, Settings  # reuse sheet config and behavior
from src.connectors.base import ConnectorConfig, connector_from_config


@dataclass
class ConnectorSettings:
    connectors: List[ConnectorConfig]


def _load_connector_settings(path: str = "config/connectors.yml") -> ConnectorSettings:
    if yaml is None or not os.path.exists(path):
        logger.warning("No connectors config found; skipping connector sync.")
        return ConnectorSettings(connectors=[])
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    conns: List[ConnectorConfig] = []
    for c in data.get("connectors", []) or []:
        conns.append(
            ConnectorConfig(
                provider=c.get("provider", "").strip(),
                account_name=c.get("account", "").strip(),
                credentials=c.get("credentials", {}) or {},
                options=c.get("options", {}) or {},
            )
        )
    return ConnectorSettings(connectors=conns)


def _base_key(rec: dict) -> Tuple[str, str, str, str]:
    return (
        rec.get("Date", ""),
        rec.get("Amount", ""),
        rec.get("Name", ""),
        rec.get("Merchant", ""),
    )


def main():
    settings = _load_settings()
    cset = _load_connector_settings()
    if not cset.connectors:
        logger.info("connector_sync.no_connectors configured")
        return

    accounts: Dict[str, AccountCfg] = {a.name: a for a in settings.accounts}
    for ccfg in cset.connectors:
        acct = accounts.get(ccfg.account_name)
        if not acct:
            logger.error(f"connector_sync.missing_account account={ccfg.account_name}")
            continue
        target_sheet_id = acct.sheet_id or settings.sheet_id
        if not target_sheet_id:
            logger.error(f"connector_sync.no_sheet_id account={acct.name}")
            continue

        # Instantiate connector
        try:
            connector = connector_from_config(ccfg)
        except Exception as e:
            logger.exception(f"connector_sync.bad_connector provider={ccfg.provider} err={e}")
            continue

        try:
            rows = list(connector.fetch())
        except NotImplementedError as e:
            logger.warning(str(e))
            continue
        except Exception as e:
            logger.exception(f"connector_sync.fetch_error provider={ccfg.provider} err={e}")
            continue

        existing = fetch_existing_rows(
            sheet_id=target_sheet_id,
            worksheet_name=acct.worksheet,
            json_keyfile_path=settings.service_account_keyfile,
        )

        # Dedupe: use account's configured mode
        to_upload: List[Dict[str, str]] = []
        if getattr(acct, "dedupe", "frequency") == "strict":
            seen = set(_base_key(r) for r in existing)
            for r in rows:
                k = _base_key(r)
                if k in seen:
                    continue
                seen.add(k)
                to_upload.append(r)
        else:
            # frequency-aware: number of occurrences in source minus existing
            from collections import Counter
            src_counter = Counter(_base_key(r) for r in rows)
            existing_counter = Counter(_base_key(r) for r in existing)
            allowance = {k: max(0, src_counter[k] - existing_counter[k]) for k in src_counter}
            for r in rows:
                k = _base_key(r)
                if allowance.get(k, 0) > 0:
                    to_upload.append(r)
                    allowance[k] -= 1

        if not to_upload:
            logger.info(f"connector_sync.no_new_rows account={acct.name}")
            continue

        appended = append_rows(
            sheet_id=target_sheet_id,
            worksheet_name=acct.worksheet,
            rows=to_upload,
            json_keyfile_path=settings.service_account_keyfile,
        )
        logger.info(
            f"connector_sync.append account={acct.name} worksheet='{acct.worksheet}' appended={appended}"
        )

        # Optional sort
        if appended > 0 and getattr(acct, "sort_column", None):
            sort_worksheet(
                sheet_id=target_sheet_id,
                worksheet_name=acct.worksheet,
                sort_by=getattr(acct, "sort_column"),
                ascending=bool(getattr(acct, "sort_ascending", False)),
                json_keyfile_path=settings.service_account_keyfile,
            )


if __name__ == "__main__":
    main()
