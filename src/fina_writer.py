import csv
from typing import Dict, Iterable

FinaRow = Dict[str, str]

FIELDNAMES = [
    "Date",
    "Amount",
    "Name",
    "Merchant",
    "txn_id",
    "Category",
    "Currency",
    "City",
    "Region",
]


def write_fina_csv(rows: Iterable[FinaRow], out_path: str) -> None:
    with open(out_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
