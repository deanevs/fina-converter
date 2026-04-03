import hashlib
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional, Tuple

FinaRow = Dict[str, str]
LegacyKey = Tuple[str, str, str, str]


def norm_text(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def norm_amount(value: str) -> str:
    raw = (value or "").strip()
    neg = False
    if raw.startswith("(") and raw.endswith(")"):
        neg = True
        raw = raw[1:-1]
    raw = raw.replace(",", "")
    raw = re.sub(r"[^0-9.\-]", "", raw)
    try:
        amount = Decimal(raw)
        if neg:
            amount = -amount
    except (InvalidOperation, ValueError):
        amount = Decimal("0")
    return f"{amount:.2f}"


def legacy_key(rec: FinaRow) -> LegacyKey:
    return (
        (rec.get("Date", "") or "").strip(),
        norm_amount(rec.get("Amount", "")),
        norm_text(rec.get("Name", "")),
        norm_text(rec.get("Merchant", "")),
    )


def get_txn_id(rec: FinaRow) -> str:
    return (rec.get("txn_id", "") or "").strip()


def make_txn_id(*parts: object) -> str:
    base = "|".join(norm_text(str(part)) for part in parts)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


class DedupeState:
    def __init__(self, existing: Iterable[FinaRow]):
        self.seen_txn_ids = set()
        self.seen_legacy_all = set()
        self.remaining_legacy_all = Counter()
        self.remaining_legacy_without_txn = Counter()

        for rec in existing:
            current_legacy = legacy_key(rec)
            self.seen_legacy_all.add(current_legacy)
            self.remaining_legacy_all[current_legacy] += 1

            txn_id = get_txn_id(rec)
            if txn_id:
                self.seen_txn_ids.add(txn_id)
            else:
                self.remaining_legacy_without_txn[current_legacy] += 1

    def allow_strict(self, rec: FinaRow) -> bool:
        txn_id = get_txn_id(rec)
        current_legacy = legacy_key(rec)

        if txn_id:
            if txn_id in self.seen_txn_ids:
                return False
            if self.remaining_legacy_without_txn[current_legacy] > 0:
                return False
            self.seen_txn_ids.add(txn_id)
            return True

        if current_legacy in self.seen_legacy_all:
            return False

        self.seen_legacy_all.add(current_legacy)
        return True

    def allow_frequency(self, rec: FinaRow) -> bool:
        txn_id = get_txn_id(rec)
        current_legacy = legacy_key(rec)

        if txn_id:
            if txn_id in self.seen_txn_ids:
                return False
            if self.remaining_legacy_without_txn[current_legacy] > 0:
                self.remaining_legacy_without_txn[current_legacy] -= 1
                return False
            self.seen_txn_ids.add(txn_id)
            return True

        if self.remaining_legacy_all[current_legacy] > 0:
            self.remaining_legacy_all[current_legacy] -= 1
            return False

        return True


def row_amount(rec: FinaRow) -> float:
    try:
        return float(norm_amount(rec.get("Amount", "0")))
    except Exception:
        return 0.0


def filter_upload_rows(
    rows: List[FinaRow],
    existing: Iterable[FinaRow],
    mode: str = "frequency",
    threshold: Optional[float] = None,
) -> List[FinaRow]:
    state = DedupeState(existing)
    selected: List[FinaRow] = []

    for rec in rows:
        if mode == "strict":
            allowed = state.allow_strict(rec)
        elif mode in ("smart", "hybrid") and threshold is not None:
            if abs(row_amount(rec)) <= float(threshold):
                allowed = state.allow_frequency(rec)
            else:
                allowed = state.allow_strict(rec)
        else:
            allowed = state.allow_frequency(rec)

        if allowed:
            selected.append(rec)

    return selected
