import hashlib
from typing import Dict, Iterable, Iterator, Set

from src.transaction_identity import get_txn_id, legacy_key

FinaRow = Dict[str, str]


def txn_fingerprint(row: FinaRow, salt: str = "") -> str:
    txn_id = get_txn_id(row)
    if txn_id:
        base = f"txn_id|{txn_id}|{salt}"
    else:
        date, amt, name, merchant = legacy_key(row)
        base = f"{date}|{amt}|{name}|{merchant}|{salt}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def filter_new(rows: Iterable[FinaRow], seen_hashes: Set[str], salt: str = "") -> Iterator[FinaRow]:
    for r in rows:
        fp = txn_fingerprint(r, salt)
        if fp in seen_hashes:
            continue
        seen_hashes.add(fp)
        yield r
