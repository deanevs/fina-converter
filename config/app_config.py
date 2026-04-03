from dataclasses import dataclass
import os


@dataclass
class AppConfig:
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    ENABLE_JSON_LOGS: bool = os.getenv("ENABLE_JSON_LOGS", "0").lower() in ("1","true","yes")

app_config = AppConfig()
