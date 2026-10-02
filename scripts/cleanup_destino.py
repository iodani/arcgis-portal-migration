#!/usr/bin/env python3
"""Elimina items de prueba en el portal DESTINO.

Comando aislado para no tener que borrar manualmente cada vez que se hace
una prueba. No depende de ningun estado/mapeo de migracion: borra por
carpeta destino (--folder) y/o por itemId puntual (--item-id, repetible),
asi que tambien sirve para items creados fuera de este toolkit (por
ejemplo, pruebas manuales).

SIEMPRE opera sobre el portal DESTINO (variables DESTINO_* en .env).
Nunca toca el portal origen.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from arcgis.gis import GIS  # noqa: E402

from migracion_esri.config import get_env, load_config  # noqa: E402
from migracion_esri.logging_setup import log_error_context, setup_logging  # noqa: E402
from migracion_esri.workflow_ui import (  # noqa: E402
    WorkflowSummary,
    print_failure_summary,
    print_summary,
)


def connect_destino(logger):
    gis = GIS(get_env("DESTINO_URL"), get_env("DESTINO_USER"), get_env("DESTINO_PASS"))
    logger.info("Portal destino conectado: user=%s url=%s", gis.users.me.username, gis.url)
    return gis


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Elimina items en el portal DESTINO, por carpeta y/o por itemId puntual"
    )
    parser.add_argument("--folder", default=None, help="Carpeta destino a vaciar y eliminar")
    parser.add_argument(
        "--item-id",
        action="append",
        default=[],
        dest="item_ids",
        help="itemId puntual a eliminar en destino (repetible)",
    )
    parser.add_argument(
        "--owner",
        default=None,
        help="Owner a filtrar en --folder (default: usuario DESTINO_USER)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo listar, sin eliminar")
    args = parser.parse_args()

    if not args.folder and not args.item_ids:
        parser.error("Debe indicar --folder y/o --item-id (al menos uno)")

    load_config()
    logger = setup_logging("cleanup_destino")
    logger.info("=== INICIO cleanup_destino (dry_run=%s) ===", args.dry_run)

    deleted = 0
    not_found = 0
    errors = 0

    try:
        gis_destino = connect_destino(logger)
        owner = args.owner or gis_destino.users.me.username

        targets: list[str] = list(args.item_ids)

        if args.folder:
            logger.info("Buscando items en carpeta destino=%s owner=%s", args.folder, owner)
            found = gis_destino.content.search(
                query=f"owner:{owner} folder:{args.folder}",
                max_items=300,
            )
            targets.extend(item.id for item in found)
            logger.info("Items encontrados en carpeta: %d", len(found))

        targets = list(dict.fromkeys(targets))  # dedupe conservando orden
        logger.info("Items a procesar: %d", len(targets))

        for item_id in targets:
            try:
                item = gis_destino.content.get(item_id)
            except Exception as exc:
                errors += 1
                log_error_context(
                    logger, "cleanup_destino", "Error consultando item", id_nuevo=item_id, exc=exc
                )
                continue

            if item is None:
                not_found += 1
                logger.warning("No encontrado en destino: %s", item_id)
                continue

            logger.info(
                "%s: %s (%s)", "DRY-RUN" if args.dry_run else "Eliminando", item.title, item_id
            )
            if args.dry_run:
                deleted += 1
                continue
            try:
                item.delete()
                deleted += 1
            except Exception as exc:
                errors += 1
                log_error_context(
                    logger,
                    "cleanup_destino",
                    "Fallo al eliminar",
                    id_nuevo=item_id,
                    titulo=item.title,
                    exc=exc,
                )

        if args.folder and not args.dry_run and errors == 0:
            try:
                remaining = gis_destino.content.search(
                    query=f"owner:{owner} folder:{args.folder}", max_items=1
                )
                if not remaining:
                    gis_destino.content.folders.delete(args.folder)
                    logger.info("Carpeta eliminada: %s", args.folder)
                else:
                    logger.info("Carpeta %s aun tiene items; no se elimina", args.folder)
            except Exception as exc:
                logger.warning("No se pudo verificar/eliminar carpeta %s: %s", args.folder, exc)

        summary = WorkflowSummary(
            script="cleanup_destino",
            lines=[
                f" Items procesados: {len(targets)}",
                f" Eliminados: {deleted}",
                f" No encontrados: {not_found}",
                f" Errores: {errors}",
                f" Modo dry-run: {args.dry_run}",
            ],
            errors=errors,
        )
        print_summary(summary, logger)
        return 0 if errors == 0 else 1

    except Exception as exc:
        log_error_context(logger, "cleanup_destino", "Limpieza abortada", exc=exc)
        print_failure_summary("cleanup_destino", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
