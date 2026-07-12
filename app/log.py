import logging
import os
from logging.handlers import RotatingFileHandler

LOG_PATH = os.path.join("database", "newsletterr.log")
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3

def setup_logging():
    """Configure root logging once; LOG_LEVEL env overrides (default INFO).
    Logs go to stdout (captured by Docker) and to a rotating file under
    database/ so they survive restarts and can be exported."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    os.makedirs("database", exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=[stream_handler, file_handler])
