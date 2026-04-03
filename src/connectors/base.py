"""
Connector interfaces for fetching transactions directly from providers (e.g., Open Banking).

This is a scaffold: implement concrete connectors (TrueLayer, SaltEdge, etc.) and
plug them into connector_sync.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

FinaRow = Dict[str, str]


@dataclass
class ConnectorConfig:
    provider: str
    account_name: str  # maps to accounts.yml account for sheet_id/worksheet
    credentials: Dict[str, str]  # provider-specific (client_id, secret, access_token, etc.)
    options: Dict[str, str] | None = None


class BaseConnector(ABC):
    def __init__(self, cfg: ConnectorConfig):
        self.cfg = cfg

    @abstractmethod
    def fetch(self, since_iso_date: Optional[str] = None) -> Iterable[FinaRow]:
        """
        Yield Fina rows. since_iso_date is YYYY-MM-DD to limit range.
        Must map provider fields to the Fina schema:
        Date, Amount, Name, Merchant, txn_id, Category, Currency, City, Region
        """
        ...


def connector_from_config(cfg: ConnectorConfig) -> BaseConnector:
    provider = cfg.provider.lower()
    if provider == "truelayer":
        from .truelayer import TrueLayerConnector
        return TrueLayerConnector(cfg)
    raise ValueError(f"Unsupported provider: {cfg.provider}")
