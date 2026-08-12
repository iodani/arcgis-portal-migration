import logging
import sys
import time
from pathlib import Path

from migracion_esri.config import LOGS_DIR, ensure_dirs


def setup_logging(script_name: str) -> logging.Logger:
    ensure_dirs()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"{script_name}_{timestamp}.log"

    logger = logging.getLogger(script_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.info("Log iniciado: %s", log_path)
    return logger


def log_error_context(
    logger: logging.Logger,
    script: str,
    message: str,
    *,
    portal: str | None = None,
    fase: str | None = None,
    id_viejo: str | None = None,
    titulo: str | None = None,
    exc: Exception | None = None,
) -> None:
    parts = [f"{script}"]
    if fase:
        parts.append(f"fase={fase}")
    if portal:
        parts.append(f"portal={portal}")
    if id_viejo:
        parts.append(f"item={id_viejo}")
    if titulo:
        parts.append(f"titulo={titulo}")
    prefix = " | ".join(parts)
    detail = message
    if exc is not None:
        detail = f"{type(exc).__name__}: {exc}"
    logger.error("%s | %s", prefix, detail)
