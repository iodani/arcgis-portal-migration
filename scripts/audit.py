#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import INVENTARIO_CARPETAS, load_config
from migracion_esri.content_search import fetch_all_items, item_value
from migracion_esri.drivers.registry import get_driver_name, get_fase
from migracion_esri.folders import build_folder_map
from migracion_esri.gis_client import validate_connections
from migracion_esri.logging_setup import setup_logging, log_error_context
from migracion_esri.workflow_ui import WorkflowSummary, print_failure_summary, print_summary

AUDIT_COLUMNS = [
    "Titulo",
    "ID_Viejo",
    "URL_Vieja",
    "Carpeta_Origen",
    "Tamaño_MB",
    "Type",
    "Fase",
    "Driver",
]


def main() -> int:
    load_config()
    logger = setup_logging("audit")
    logger.info("=== INICIO audit ===")

    try:
        gis_origen, _, _, _ = validate_connections(logger)
        folder_map = build_folder_map(gis_origen)

        logger.info("Buscando todo el contenido accesible en origen...")
        items = fetch_all_items(gis_origen, logger)

        carpetas = set()
        total_mb = 0.0
        type_counts: dict[str, int] = {}

        with open(INVENTARIO_CARPETAS, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(AUDIT_COLUMNS)
            for item in items:
                item_type = item_value(item, "type") or "Unknown"
                size_bytes = item_value(item, "size") or 0
                size_mb = round(size_bytes / (1024 * 1024), 2)
                owner_folder = item_value(item, "ownerFolder")
                nombre_carpeta = folder_map.get(owner_folder, "RAIZ")
                fase = get_fase(item_type)
                driver = get_driver_name(item_type)

                carpetas.add(nombre_carpeta)
                total_mb += size_mb
                type_counts[item_type] = type_counts.get(item_type, 0) + 1

                writer.writerow([
                    item_value(item, "title", ""),
                    item_value(item, "id", ""),
                    item_value(item, "url", "") or "",
                    nombre_carpeta,
                    size_mb,
                    item_type,
                    fase,
                    driver,
                ])

        summary = WorkflowSummary(
            script="audit",
            lines=[
                f" Items inventariados: {len(items)}",
                f" Types distintos: {len(type_counts)}",
                f" Carpetas distintas: {len(carpetas)}",
                f" Tamaño total (MB): {round(total_mb, 2)}",
                f" Archivo: {INVENTARIO_CARPETAS}",
            ],
            next_command="python scripts/prepare_pilot.py",
            next_hint="Generar inventario piloto (1 por Type) o prepare.py para inventario completo",
        )
        print_summary(summary, logger)
        return 0
    except Exception as exc:
        log_error_context(logger, "audit", "Auditoría fallida", portal="origen", exc=exc)
        print_failure_summary("audit", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
