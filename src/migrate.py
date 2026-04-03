from typing import Tuple, List, Dict
from collections import Counter

from src.sheets import fetch_existing_rows, append_rows
from src.dedupe import txn_fingerprint

FinaRow = Dict[str, str]


def migrate_sheet(
    src_sheet_id: str,
    src_worksheet: str,
    dst_sheet_id: str,
    dst_worksheet: str,
    json_keyfile_path: str,
) -> Tuple[int, int, int]:
    """
    Copy historical rows from source sheet/tab to destination sheet/tab,
    skipping duplicates using a simple fingerprint. Returns a tuple of
    (source_count, already_in_dest_count, appended_count).
    """
    # Fetch source and destination rows
    src_rows: List[FinaRow] = fetch_existing_rows(src_sheet_id, src_worksheet, json_keyfile_path)
    dst_rows: List[FinaRow] = fetch_existing_rows(dst_sheet_id, dst_worksheet, json_keyfile_path)

    # Frequency-aware allowance based on fingerprints so duplicates counts are preserved
    src_counts = Counter(txn_fingerprint(r) for r in src_rows)
    dst_counts = Counter(txn_fingerprint(r) for r in dst_rows)
    allowance = {k: max(0, src_counts[k] - dst_counts[k]) for k in src_counts}

    to_append: List[FinaRow] = []
    skipped = 0
    for r in src_rows:
        fp = txn_fingerprint(r)
        if allowance.get(fp, 0) > 0:
            to_append.append(r)
            allowance[fp] -= 1
        else:
            skipped += 1

    appended = 0
    if to_append:
        appended = append_rows(dst_sheet_id, dst_worksheet, to_append, json_keyfile_path)

    return (len(src_rows), skipped, appended)
