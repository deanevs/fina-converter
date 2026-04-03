import csv
from datetime import datetime
from typing import Dict, Iterable, Iterator, List
from src.utils.logger import logger

FinaRow = Dict[str, str]


def _parse_amount(debit: str, credit: str) -> float:
    debit = (debit or "").replace(",", "").strip()
    credit = (credit or "").replace(",", "").strip()
    if debit:
        return -float(debit)
    if credit:
        return float(credit)
    raise ValueError("Missing both debit and credit amount")


def parse_lloyds_csv(path: str, currency: str = "GBP") -> Iterator[FinaRow]:
    """
    Parse a Lloyds CSV export with headers like:
    Transaction Date, Transaction Type, Sort Code, Account Number,
    Transaction Description, Debit Amount, Credit Amount, Balance

    Yields rows in Fina format: Date, Amount, Name, Merchant, Category,
    Currency, City, Region
    """
    with open(path, mode="r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Normalize fieldnames once to detect schema
        fieldnames: List[str] = [fn.strip() for fn in (reader.fieldnames or [])]
        is_credit_schema = "Transaction Amount" in fieldnames
        logger.debug(f"lloyds.detect schema=credit:{is_credit_schema} fields={fieldnames}")

        for raw in reader:
            row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
            try:
                date_str = row.get("Transaction Date") or row.get("Date")
                # Lloyds exports use dd/mm/YYYY
                date_iso = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception as e:
                logger.debug(f"lloyds.parse skip row due to date error: {e} row={row}")
                continue

            desc = row.get("Transaction Description", "") or row.get("Description", "")

            try:
                if is_credit_schema:
                    amt_str = (row.get("Transaction Amount", "") or "").replace(",", "")
                    if amt_str == "":
                        raise ValueError("empty amount")
                    # Credit card CSV: positive values are purchases (outflow), negatives are payments/refunds (inflow)
                    # Map to Fina: outflow negative, inflow positive
                    raw_amt = float(amt_str)
                    amount = -raw_amt
                else:
                    amount = _parse_amount(row.get("Debit Amount", ""), row.get("Credit Amount", ""))
            except Exception as e:
                logger.debug(f"lloyds.parse skip row due to amount error: {e} row={row}")
                continue

            fina_row: FinaRow = {
                "Date": date_iso,
                "Amount": f"{amount:.2f}",
                "Name": desc,
                "Merchant": desc,
                "Category": "",
                "Currency": currency,
                "City": "",
                "Region": "",
            }
            yield fina_row
