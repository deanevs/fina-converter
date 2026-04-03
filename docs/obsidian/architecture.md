---
tags: [architecture, diagrams]
---

# Architecture Overview

Auto-sync centric view with minimal moving parts.

## Top-level

```mermaid
flowchart TD
  user[User] -->|runs| auto_sync[src/auto_sync.py]
  auto_sync -->|reads| config[config/accounts.yml]
  auto_sync -->|parses| banks_lloyds[src/banks/lloyds.py]
  auto_sync -->|dedupe+append| sheets[src/sheets.py]
  sheets -->|Google Sheets API| gspread
  auto_sync --> logger[src/utils/logger.py]
```

## sheets internals

```mermaid
flowchart LR
  auth[_client_from_service_account] --> client[gspread client]
  client --> open[open_by_key]
  open --> ws[worksheet]
  append[append_rows] -->|ensure header| ws
  append -->|chunked append| ws
  fetch[fetch_existing_rows] --> ws
  sort[sort_worksheet] --> ws
```

Notes
- Tabs are created on demand with the Fina header
- Sorting via batchUpdate after appends (config-driven)
