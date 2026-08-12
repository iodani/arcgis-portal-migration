#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import DATA_INPUT, MAPEO_MIGRACION, load_config
from migracion_esri.folders import build_folder_map
from migracion_esri.gis_client import validate_connections
from migracion_esri.logging_setup import setup_logging, log_error_context
from migracion_esri.migrator import ItemMigrator
from migracion_esri.state import MigrationItem, MigrationState
from migracion_esri.workflow_ui import WorkflowSummary, print_failure_summary, print_summary


def load_inventory() -> list[MigrationItem]:
    if not DATA_INPUT.exists():
        raise FileNotFoundError(
            f"No existe {DATA_INPUT}. Copie data/input/inventario_migracion.example.csv "
            "y complete las filas a migrar."
        )
    df = pd.read_csv(DATA_INPUT)
    required = {"Titulo", "ID_Viejo"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Columnas faltantes en inventario: {', '.join(sorted(missing))}")

    items = []
    for _, row in df.iterrows():
        id_viejo = str(row["ID_Viejo"]).strip()
        if not id_viejo or id_viejo.lower() == "nan":
            continue
        url = row.get("URL_Vieja", "")
        carpeta = row.get("Carpeta_Origen", "RAIZ")
        items.append(
            MigrationItem(
                id_viejo=id_viejo,
                titulo=str(row["Titulo"]),
                url_vieja="" if pd.isna(url) else str(url),
                carpeta_origen="RAIZ" if pd.isna(carpeta) else str(carpeta),
            )
        )
    if not items:
        raise ValueError(f"{DATA_INPUT} no contiene filas válidas para migrar")
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Migración masiva ArcGIS con resume")
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Reintentar items en estado error además de pending/in_progress",
    )
    args = parser.parse_args()

    load_config()
    logger = setup_logging("migrate")
    logger.info("=== INICIO migrate (retry_errors=%s) ===", args.retry_errors)

    success_count = 0
    error_count = 0

    try:
        inventory = load_inventory()
        state = MigrationState()
        state.upsert_from_inventory(inventory)
        to_process = state.get_items_to_process(retry_errors=args.retry_errors)
        total = len(to_process)
        logger.info("Items a procesar: %d", total)

        if total == 0:
            counts = state.counts()
            summary = WorkflowSummary(
                script="migrate",
                lines=[
                    " No hay items pendientes de procesar.",
                    f" Exitos acumulados: {counts['success']}",
                    f" Errores acumulados: {counts['error']}",
                ],
                next_command="python scripts/report.py",
                next_hint="Generar reporte final de migración",
            )
            print_summary(summary, logger)
            return 0

        gis_origen, gis_destino, _, _ = validate_connections(logger)
        folder_map = build_folder_map(gis_origen)
        migrator = ItemMigrator(gis_origen, gis_destino, logger, folder_map)

        for index, item in enumerate(to_process, start=1):
            logger.info("--- [%d/%d] Procesando: %s ---", index, total, item.titulo)
            state.set_in_progress(item.id_viejo)
            try:
                result = migrator.migrate_item(
                    item.id_viejo, item.titulo, item.carpeta_origen
                )
                state.set_success(item.id_viejo, result.id_nuevo, result.url_nueva)
                success_count += 1
                logger.info(
                    "[%s] OK id_nuevo=%s url=%s",
                    item.titulo,
                    result.id_nuevo,
                    result.url_nueva,
                )
            except Exception as exc:
                error_count += 1
                log_error_context(
                    logger,
                    "migrate",
                    "Item no migrado",
                    id_viejo=item.id_viejo,
                    titulo=item.titulo,
                    exc=exc,
                )
                state.set_error(item.id_viejo, str(exc))
            time.sleep(1)

        counts = state.counts()
        pending = counts["pending"] + counts["in_progress"]
        if pending > 0:
            next_cmd = "python scripts/migrate.py"
            next_hint = f"Quedan {pending} items pendientes; reejecute para continuar"
        else:
            next_cmd = "python scripts/report.py"
            next_hint = "Generar reporte final de migracion"

        summary = WorkflowSummary(
            script="migrate",
            lines=[
                f" Procesados en esta ejecucion: {total}",
                f" Exitos esta ejecucion: {success_count}",
                f" Errores esta ejecucion: {error_count}",
                f" Exitos acumulados: {counts['success']}",
                f" Errores acumulados: {counts['error']}",
                f" Pendientes: {pending}",
                f" Mapeo: {MAPEO_MIGRACION}",
            ],
            errors=error_count,
            next_command=next_cmd,
            next_hint=next_hint,
        )
        print_summary(summary, logger)
        return 0 if error_count == 0 else 1

    except Exception as exc:
        log_error_context(logger, "migrate", "Migración abortada", exc=exc)
        print_failure_summary("migrate", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
