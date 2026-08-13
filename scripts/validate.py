#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import load_config
from migracion_esri.gis_client import validate_connections
from migracion_esri.logging_setup import setup_logging, log_error_context
from migracion_esri.workflow_ui import WorkflowSummary, print_failure_summary, print_summary


def main() -> int:
    load_config()
    logger = setup_logging("validate")
    logger.info("=== INICIO validate ===")

    try:
        _, _, origen, destino = validate_connections(logger)
        summary = WorkflowSummary(
            script="validate",
            lines=[
                f" Origen:  conectado (user={origen.username}, url={origen.url})",
                f" Destino: conectado (user={destino.username}, url={destino.url})",
            ],
            next_command="python scripts/audit.py",
            next_hint="Generar inventario multi-tipo del portal origen",
        )
        print_summary(summary, logger)
        return 0
    except Exception as exc:
        log_error_context(logger, "validate", "Validación fallida", exc=exc)
        print_failure_summary("validate", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
