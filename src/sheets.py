import os
from typing import Dict, Iterable, List, Union

from src.utils.logger import logger

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:  # dependencies may not be installed yet
    gspread = None
    Credentials = None

FinaRow = Dict[str, str]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _client_from_service_account(json_keyfile_path: str):
    if Credentials is None or gspread is None:
        logger.error("Google libraries not installed (gspread/google-auth)")
        raise RuntimeError("Google libraries not installed. Please install gspread and google-auth.")
    if not os.path.exists(json_keyfile_path):
        logger.error(f"service_account_file_missing path='{json_keyfile_path}'")
        raise FileNotFoundError(
            f"Google service account key not found at '{json_keyfile_path}'. "
            "Ensure the file exists and your config points to the correct path."
        )
    creds = Credentials.from_service_account_file(json_keyfile_path, scopes=SCOPES)
    return gspread.authorize(creds)


def append_rows(sheet_id: str, worksheet_name: str, rows: Iterable[FinaRow], json_keyfile_path: str) -> int:
    client = _client_from_service_account(json_keyfile_path)
    logger.debug(f"sheets.append_rows open sheet_id={sheet_id} worksheet='{worksheet_name}'")
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(worksheet_name)
    except Exception as e:
        # Auto-create worksheet only if it doesn't exist
        try:
            from gspread.exceptions import WorksheetNotFound  # type: ignore
        except Exception:
            WorksheetNotFound = None  # type: ignore
        if WorksheetNotFound and isinstance(e, WorksheetNotFound):  # type: ignore
            from src.fina_writer import FIELDNAMES
            ws = sh.add_worksheet(title=worksheet_name, rows=1000, cols=len(FIELDNAMES))
            logger.info(f"sheets.created_worksheet title='{worksheet_name}'")
            # Initialize header
            ws.update('1:1', [FIELDNAMES])
        else:
            raise
    # Determine header row; if missing, set to Fina FIELDNAMES
    from src.fina_writer import FIELDNAMES
    header: List[str] = ws.row_values(1)
    if not header:
        # Set the header row to the expected Fina schema
        logger.info(f"sheets.set_header worksheet='{worksheet_name}' header={FIELDNAMES}")
        ws.update('1:1', [FIELDNAMES])
        header = FIELDNAMES
    else:
        # If required fields are missing, prefer FIELDNAMES order for mapping
        required = set(["Date", "Amount", "Name", "Merchant", "txn_id", "Category", "Currency", "City", "Region"])
        header_stripped = [h.strip() for h in header]
        if not required.issubset(set(header_stripped)):
            header = FIELDNAMES
            header_stripped = FIELDNAMES
            ws.update('1:1', [FIELDNAMES])
    # Map using stripped header keys to avoid whitespace mismatches
    header_stripped = [h.strip() for h in header]
    out_rows: List[List[str]] = []
    for r in rows:
        out_rows.append([r.get(hk, "") for hk in header_stripped])
    if not out_rows:
        return 0
    # Append in chunks to avoid potential API issues with large payloads
    total = 0
    CHUNK = 200
    for i in range(0, len(out_rows), CHUNK):
        chunk = out_rows[i:i+CHUNK]
        ws.append_rows(chunk, value_input_option="USER_ENTERED")
        total += len(chunk)
    logger.info(f"sheets.append_rows appended={total} worksheet='{worksheet_name}'")
    return total


def fetch_existing_rows(sheet_id: str, worksheet_name: str, json_keyfile_path: str) -> List[FinaRow]:
    """Return existing rows as list of dicts using the current header.
    If no header, returns an empty list.
    """
    client = _client_from_service_account(json_keyfile_path)
    logger.debug(f"sheets.fetch_existing open sheet_id={sheet_id} worksheet='{worksheet_name}'")
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(worksheet_name)
    except Exception as e:
        # If worksheet doesn't exist yet, treat as empty; otherwise re-raise
        try:
            from gspread.exceptions import WorksheetNotFound  # type: ignore
        except Exception:
            WorksheetNotFound = None  # type: ignore
        if WorksheetNotFound and isinstance(e, WorksheetNotFound):  # type: ignore
            logger.info(f"sheets.worksheet_missing worksheet='{worksheet_name}', returning empty list")
            return []
        raise
    header: List[str] = ws.row_values(1)
    if not header:
        return []
    # get_all_records uses the first row as header by default
    records = ws.get_all_records(default_blank="")
    # Ensure keys match header capitalization/spacing used in Fina
    # gspread normalizes keys from the header row, so we pass through
    return [
        {k.strip(): (str(v) if v is not None else "") for k, v in rec.items()}
        for rec in records
    ]


def sort_worksheet(
    sheet_id: str,
    worksheet_name: str,
    sort_by: Union[str, int] = "Date",
    ascending: bool = False,
    json_keyfile_path: str = "credentials/service_account.json",
) -> None:
    """Sort a worksheet in-place by column using Sheets batchUpdate.

    sort_by: column header name (e.g., "Date") or 1-based column index (e.g., 1)
    ascending: True=ASC, False=DESC (default newest first for Date)
    """
    client = _client_from_service_account(json_keyfile_path)
    sh = client.open_by_key(sheet_id)
    # If the worksheet doesn't exist, skip sorting
    try:
        ws = sh.worksheet(worksheet_name)
    except Exception:
        logger.info(f"sheets.sort.skip_missing worksheet='{worksheet_name}'")
        return

    # Determine 0-based column index for sorting
    header: List[str] = ws.row_values(1)
    col_idx0: int = 0
    if isinstance(sort_by, int):
        col_idx0 = max(0, sort_by - 1)
    else:
        # map header name to index
        try:
            col_idx0 = [h.strip() for h in header].index(sort_by)
        except Exception:
            # fallback to first column
            col_idx0 = 0

    # Use the full grid from row 2 down to the sheet's row_count
    # Sorting entire grid is fine; header is preserved by starting at row 2
    order = "ASCENDING" if ascending else "DESCENDING"
    requests = [
        {
            "sortRange": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": 1,
                    "startColumnIndex": 0,
                },
                "sortSpecs": [
                    {"dimensionIndex": col_idx0, "sortOrder": order}
                ],
            }
        }
    ]
    sh.batch_update({"requests": requests})
    logger.info(
        f"sheets.sorted worksheet='{worksheet_name}' by='{sort_by}' ascending={ascending}"
    )
