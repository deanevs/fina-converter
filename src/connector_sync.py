"""
Connector-based sync runner: fetch transactions from configured providers and append to Google Sheets
with dedupe and optional sorting.

Usage:
  uv run python -m src.connector_sync

Config: see config/connectors.example.yml
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List

try:
    import yaml
except Exception:
    yaml = None

from src.connectors.base import ConnectorConfig, connector_from_config
from src.personal_sync import (  # reuse sheet config and behavior
    AccountCfg,
    _load_settings,
)
from src.sheets import append_rows, fetch_existing_rows, sort_worksheet
from src.transaction_identity import filter_upload_rows
from src.utils.logger import logger


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

        to_upload = filter_upload_rows(
            rows,
            existing,
            mode=getattr(acct, "dedupe", "frequency"),
            threshold=getattr(acct, "small_amount_threshold", None),
        )

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
