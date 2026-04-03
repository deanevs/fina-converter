import argparse
import os
from typing import Iterable, Dict

from src.banks import parse_lloyds_csv
from src.fina_writer import write_fina_csv, FIELDNAMES
from src.dedupe import filter_new
from src.utils.logger import logger

try:
    import yaml
except Exception:
    yaml = None


def _load_config(path: str) -> Dict:
    if yaml is None:
        raise RuntimeError("PyYAML not installed. Please install pyyaml.")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def convert_cmd(args):
    bank = args.bank.lower()
    currency = args.currency
    input_path = args.input
    output = args.output

    if bank == "lloyds":
        rows = parse_lloyds_csv(input_path, currency=currency)
    else:
        raise SystemExit(f"Unsupported bank: {bank}")

    write_fina_csv(rows, output)
    logger.info(f"Wrote {output}")


def upload_cmd(args):
    from src.sheets import append_rows
    cfg = _load_config(args.config)
    acct = cfg["accounts"][args.account]
    bank = acct["bank"]
    currency = acct.get("currency", "GBP")
    sheet_id = acct["sheet_id"]
    worksheet = acct.get("worksheet", "Transactions")
    keyfile = cfg["google"]["service_account_keyfile"]

    # Convert source
    if bank == "lloyds":
        rows_iter = parse_lloyds_csv(args.input, currency=currency)
    else:
        raise SystemExit(f"Unsupported bank: {bank}")

    # Append to Sheets
    count = append_rows(sheet_id, worksheet, rows_iter, keyfile)
    logger.info(f"Appended {count} rows to sheet {sheet_id}/{worksheet}")


def sync_cmd(args):
    # Simple wrapper: optionally write a local CSV, then upload directly from the bank CSV
    if args.output:
        convert_cmd(argparse.Namespace(bank=args.bank, currency=args.currency, input=args.input, output=args.output))
    upload_cmd(argparse.Namespace(config=args.config, account=args.account, input=args.input))


def main():
    parser = argparse.ArgumentParser(description="Fina converter and sync")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_convert = sub.add_parser("convert", help="Convert bank CSV to Fina CSV")
    p_convert.add_argument("--bank", required=True, help="lloyds")
    p_convert.add_argument("--input", required=True, help="Input CSV path")
    p_convert.add_argument("--output", required=True, help="Output CSV path")
    p_convert.add_argument("--currency", default="GBP")
    p_convert.set_defaults(func=convert_cmd)

    p_upload = sub.add_parser("upload", help="Upload rows to Google Sheets from bank CSV")
    p_upload.add_argument("--config", default="config/accounts.yml")
    p_upload.add_argument("--account", required=True)
    p_upload.add_argument("--input", required=True)
    p_upload.set_defaults(func=upload_cmd)

    p_sync = sub.add_parser("sync", help="Convert and upload in one step")
    p_sync.add_argument("--config", default="config/accounts.yml")
    p_sync.add_argument("--account", required=True)
    p_sync.add_argument("--bank", required=True)
    p_sync.add_argument("--input", required=True)
    p_sync.add_argument("--output")
    p_sync.add_argument("--currency", default="GBP")
    p_sync.set_defaults(func=sync_cmd)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
