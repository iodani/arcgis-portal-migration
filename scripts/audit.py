#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import INVENTARIO_CARPETAS, load_config
from migracion_esri.folders import build_folder_map
from migracion_esri.gis_client import validate_connections
from migracion_esri.logging_setup import setup_logging, log_error_context
from migracion_esri.workflow_ui import WorkflowSummary, print_failure_summary, print_summary


def main() -> int:
    load_config()
    logger = setup_logging("audit")
    logger.info("=== INICIO audit ===")

    try:
        gis_origen, _, _, _ = validate_connections(logger)
        logger.info("Buscando Feature Services en origen...")
        items = gis_origen.content.search(query="type:'Feature Service'", max_items=10000)
        folder_map = build_folder_map(gis_origen)

        carpetas = set()
        total_mb = 0.0
        with open(INVENTARIO_CARPETAS, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Titulo", "ID_Viejo", "URL_Vieja", "Carpeta_Origen", "Tamaño_MB"])
            for item in items:
                nombre_carpeta = folder_map.get(item.ownerFolder, "RAIZ")
                size_mb = round(item.size / (1024 * 1024), 2)
                carpetas.add(nombre_carpeta)
                total_mb += size_mb
                writer.writerow([item.title, item.id, item.url, nombre_carpeta, size_mb])
                logger.info("Inventariado: %s | carpeta=%s", item.title, nombre_carpeta)

        summary = WorkflowSummary(
            script="audit",
            lines=[
                f" Items inventariados: {len(items)}",
                f" Carpetas distintas: {len(carpetas)}",
                f" Tamaño total (MB): {round(total_mb, 2)}",
                f" Archivo: {INVENTARIO_CARPETAS}",
            ],
            next_command="python scripts/prepare.py",
            next_hint="Generar inventario de trabajo; luego editar CSV y eliminar filas no deseadas",
        )
        print_summary(summary, logger)
        return 0
    except Exception as exc:
        log_error_context(logger, "audit", "Auditoría fallida", portal="origen", exc=exc)
        print_failure_summary("audit", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
