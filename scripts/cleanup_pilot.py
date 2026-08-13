#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import DEFAULT_PILOT_FOLDER, INVENTARIO_PILOT, PILOT_STATE_DB, load_config
from migracion_esri.gis_client import validate_connections
from migracion_esri.logging_setup import setup_logging, log_error_context
from migracion_esri.state import MigrationState
from migracion_esri.workflow_ui import WorkflowSummary, print_failure_summary, print_summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Eliminar items del piloto en portal destino"
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=INVENTARIO_PILOT,
        help="CSV del inventario piloto",
    )
    parser.add_argument(
        "--pilot-folder",
        default=DEFAULT_PILOT_FOLDER,
        help="Carpeta piloto en destino",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo listar items a eliminar, sin borrar",
    )
    args = parser.parse_args()

    load_config()
    logger = setup_logging("cleanup_pilot")
    logger.info("=== INICIO cleanup_pilot (dry_run=%s) ===", args.dry_run)

    deleted = 0
    errors = 0

    try:
        if not args.inventory.exists():
            raise FileNotFoundError(f"No existe inventario piloto: {args.inventory}")

        df = pd.read_csv(args.inventory)
        id_viejos = [str(x).strip() for x in df["ID_Viejo"] if str(x).strip()]

        state = MigrationState(db_path=PILOT_STATE_DB)
        successful = state.get_successful_items(id_viejos)
        logger.info("Items exitosos a limpiar: %d", len(successful))

        if not successful:
            summary = WorkflowSummary(
                script="cleanup_pilot",
                lines=[" No hay items exitosos del piloto para eliminar."],
                next_command="python scripts/prepare_pilot.py --report",
                next_hint="Generar matriz de resultados del piloto",
            )
            print_summary(summary, logger)
            return 0

        _, gis_destino, _, _ = validate_connections(logger)

        for item in successful:
            logger.info("Eliminando: %s | id_nuevo=%s", item.titulo, item.id_nuevo)
            if args.dry_run:
                deleted += 1
                continue
            try:
                dest_item = gis_destino.content.get(item.id_nuevo)
                if dest_item:
                    dest_item.delete()
                    deleted += 1
                    logger.info("Eliminado: %s", item.titulo)
                else:
                    logger.warning("No encontrado en destino: %s", item.id_nuevo)
            except Exception as exc:
                errors += 1
                log_error_context(
                    logger,
                    "cleanup_pilot",
                    "Fallo al eliminar",
                    id_nuevo=item.id_nuevo,
                    titulo=item.titulo,
                    exc=exc,
                )

        if not args.dry_run and args.pilot_folder:
            try:
                user = gis_destino.users.me.username
                remaining = gis_destino.content.search(
                    query=f"owner:{user} folder:{args.pilot_folder}",
                    max_items=1,
                )
                if not remaining:
                    gis_destino.content.folders.delete(args.pilot_folder)
                    logger.info("Carpeta piloto eliminada: %s", args.pilot_folder)
                else:
                    logger.info("Carpeta piloto aún tiene items; no se elimina")
            except Exception as exc:
                logger.warning("No se pudo verificar/eliminar carpeta piloto: %s", exc)

        summary = WorkflowSummary(
            script="cleanup_pilot",
            lines=[
                f" Items procesados: {len(successful)}",
                f" Eliminados: {deleted}",
                f" Errores: {errors}",
                f" Modo dry-run: {args.dry_run}",
            ],
            next_command="python scripts/prepare_pilot.py --report",
            next_hint="Generar matriz tipo→resultado para el PM",
        )
        print_summary(summary, logger)
        return 0 if errors == 0 else 1

    except Exception as exc:
        log_error_context(logger, "cleanup_pilot", "Limpieza abortada", exc=exc)
        print_failure_summary("cleanup_pilot", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
