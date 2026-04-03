from loguru import logger
import sys
import os
from config import app_config

# Remove default logger
logger.remove()

# Determine logging level based on LOG_LEVEL
log_level = app_config.LOG_LEVEL if app_config.LOG_LEVEL else "INFO"

# Configure loguru logger with color formatting for console (Docker-compatible)
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
           "<level>{message}</level>",
    level=log_level,
    colorize=True  # Ensure colorized logs for Docker console
)

# Ensure logs directory exists and add file handler
os.makedirs("logs", exist_ok=True)
logger.add(
    "logs/debug.log",
    rotation="500 KB",  # Rotate the file when it reaches 500 KB
    retention="14 days",  # Retain logs for 14 days
    level=log_level,  # Use dynamic log level
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

def get_logger():
    return logger