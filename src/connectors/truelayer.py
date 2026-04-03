"""
TrueLayer connector scaffold. Requires proper OAuth flow and access_token management.
This is a placeholder for wiring later. It demonstrates how to map provider fields
into Fina rows when implemented.
"""
from __future__ import annotations

from typing import Iterable, Dict, Optional
from .base import BaseConnector, ConnectorConfig, FinaRow


class TrueLayerConnector(BaseConnector):
    def __init__(self, cfg: ConnectorConfig):
        super().__init__(cfg)
        # TODO: store access token / refresh token from cfg.credentials
        # self.access_token = cfg.credentials.get("access_token")

    def fetch(self, since_iso_date: Optional[str] = None) -> Iterable[FinaRow]:
        # TODO: implement HTTPS calls to TrueLayer Transactions endpoint
        # For now, raise to indicate not wired yet
        raise NotImplementedError(
            "TrueLayerConnector.fetch is not implemented yet. Provide access tokens and implement API calls."
        )
