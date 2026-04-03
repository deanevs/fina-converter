import hashlib
import re
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, Iterator, Set

FinaRow = Dict[str, str]


def _norm_text(s: str) -> str:
    s = (s or "").strip()
    # Collapse whitespace and lowercase for stable matching
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def _norm_amount(a: str) -> str:
    raw = (a or "").strip()
    # Remove currency symbols and commas; handle parentheses for negatives
    neg = False
    if raw.startswith("(") and raw.endswith(")"):
        neg = True
        raw = raw[1:-1]
    raw = raw.replace(",", "")
    raw = re.sub(r"[^0-9.\-]", "", raw)
    try:
        val = Decimal(raw)
        if neg:
            val = -val
    except (InvalidOperation, ValueError):
        # Fall back to zero if unparsable to avoid crashes; duplicates unlikely
        val = Decimal("0")
    # Normalize to two decimals string with sign
    return f"{val:.2f}"


def txn_fingerprint(row: FinaRow, salt: str = "") -> str:
    date = (row.get('Date', '') or '').strip()
    amt = _norm_amount(row.get('Amount', ''))
    name = _norm_text(row.get('Name', ''))
    merchant = _norm_text(row.get('Merchant', ''))
    base = f"{date}|{amt}|{name}|{merchant}|{salt}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def filter_new(rows: Iterable[FinaRow], seen_hashes: Set[str], salt: str = "") -> Iterator[FinaRow]:
    for r in rows:
        fp = txn_fingerprint(r, salt)
        if fp in seen_hashes:
            continue
        seen_hashes.add(fp)
        yield r
