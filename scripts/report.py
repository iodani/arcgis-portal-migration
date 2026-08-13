#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import ERRORES_MIGRACION, MAPEO_MIGRACION, load_config
from migracion_esri.logging_setup import setup_logging, log_error_context
from migracion_esri.state import (
    MigrationState,
    STATUS_ERROR,
    STATUS_IN_PROGRESS,
    STATUS_PENDING,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
)
from migracion_esri.workflow_ui import WorkflowSummary, print_failure_summary, print_summary


def main() -> int:
    load_config()
    logger = setup_logging("report")
    logger.info("=== INICIO report ===")

    try:
        state = MigrationState()
        counts = state.counts()
        errors = state.error_items()

        with open(ERRORES_MIGRACION, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID_Viejo", "Titulo", "URL_Vieja", "Carpeta_Origen", "Type", "Error", "Fecha",
            ])
            for item in errors:
                writer.writerow([
                    item.id_viejo,
                    item.titulo,
                    item.url_vieja,
                    item.carpeta_origen,
                    item.item_type,
                    item.error,
                    item.updated_at,
                ])
                logger.error(
                    "Item no clonado | id=%s titulo=%s type=%s error=%s",
                    item.id_viejo,
                    item.titulo,
                    item.item_type,
                    item.error,
                )

        summary = WorkflowSummary(
            script="report",
            lines=[
                f" Total registrados: {counts['total']}",
                f" Exitos: {counts[STATUS_SUCCESS]}",
                f" Errores: {counts[STATUS_ERROR]}",
                f" Skipped: {counts[STATUS_SKIPPED]}",
                f" Pendientes: {counts[STATUS_PENDING] + counts[STATUS_IN_PROGRESS]}",
                f" Mapeo CSV: {MAPEO_MIGRACION}",
                f" Errores CSV: {ERRORES_MIGRACION}",
            ],
            errors=counts[STATUS_ERROR],
            next_command="(externo) usar mapeo_migracion.csv en entorno de BD",
            next_hint="Este proyecto no actualiza la BD; entregue el CSV al equipo de datos",
        )
        print_summary(summary, logger)
        return 0
    except Exception as exc:
        log_error_context(logger, "report", "Reporte fallido", exc=exc)
        print_failure_summary("report", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
