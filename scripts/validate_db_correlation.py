#!/usr/bin/env python3
"""Fase 0: valida empiricamente la clave de correlacion entre app.arcgis_upload
y el portal ORIGEN, antes de confiar en ella para generar UPDATEs (Fase 2).

Hipotesis a validar por fila: arcgis_upload.layer_id es el itemId del
Feature Service en el portal ORIGEN, y arcgis_upload.service_url es la URL
raiz (encodedServiceURL) de ese mismo item -- igual a como lo guarda
ArcgisUploadController::actionCreate en el proyecto fdsu.

Este script es de SOLO LECTURA: no modifica arcgis_upload ni el portal.
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from arcgis.gis import GIS  # noqa: E402

from migracion_esri.config import VALIDACION_CORRELACION, get_env, load_config  # noqa: E402
from migracion_esri.db_client import fetch_arcgis_upload_rows  # noqa: E402
from migracion_esri.logging_setup import log_error_context, setup_logging  # noqa: E402
from migracion_esri.workflow_ui import (  # noqa: E402
    WorkflowSummary,
    print_failure_summary,
    print_summary,
)

RESULT_MATCH = "MATCH"
RESULT_MISMATCH = "MISMATCH"
RESULT_NOT_FOUND = "NOT_FOUND"
RESULT_EMPTY_LAYER_ID = "EMPTY_LAYER_ID"
RESULT_ERROR = "ERROR"

REPORT_COLUMNS = [
    "id",
    "client_code",
    "item_type_code",
    "service_name",
    "layer_id",
    "service_url",
    "origen_item_title",
    "origen_item_url",
    "resultado",
    "detalle",
]


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida la clave de correlacion arcgis_upload <-> portal origen (solo lectura)"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--db-dsn",
        action="store_true",
        help="Leer app.arcgis_upload via DSN Postgres (variables PG* en .env)",
    )
    source.add_argument(
        "--arcgis-upload-csv",
        type=Path,
        default=None,
        help="Leer arcgis_upload desde un CSV exportado manualmente",
    )
    parser.add_argument(
        "--only-system-account",
        action="store_true",
        help="Filtrar solo filas con is_system_account = true (requiere --db-dsn)",
    )
    args = parser.parse_args()

    load_config()
    logger = setup_logging("validate_db_correlation")
    logger.info("=== INICIO validate_db_correlation ===")

    try:
        rows = fetch_arcgis_upload_rows(
            db_dsn=args.db_dsn,
            csv_path=args.arcgis_upload_csv,
            only_system_account=args.only_system_account,
        )
        logger.info("Filas arcgis_upload a validar: %d", len(rows))

        logger.info("Conectando portal origen para resolver itemId -> url...")
        gis_origen = GIS(get_env("ORIGEN_URL"), get_env("ORIGEN_USER"), get_env("ORIGEN_PASS"))
        logger.info("Portal origen conectado: user=%s url=%s", gis_origen.users.me.username, gis_origen.url)

        counts = {
            RESULT_MATCH: 0,
            RESULT_MISMATCH: 0,
            RESULT_NOT_FOUND: 0,
            RESULT_EMPTY_LAYER_ID: 0,
            RESULT_ERROR: 0,
        }
        report_rows = []

        for row in rows:
            if not row.layer_id:
                counts[RESULT_EMPTY_LAYER_ID] += 1
                report_rows.append(
                    {
                        "id": row.id,
                        "client_code": row.client_code,
                        "item_type_code": row.item_type_code,
                        "service_name": row.service_name,
                        "layer_id": row.layer_id,
                        "service_url": row.service_url,
                        "origen_item_title": "",
                        "origen_item_url": "",
                        "resultado": RESULT_EMPTY_LAYER_ID,
                        "detalle": "layer_id vacio en arcgis_upload",
                    }
                )
                continue

            try:
                item = gis_origen.content.get(row.layer_id)
            except Exception as exc:
                counts[RESULT_ERROR] += 1
                log_error_context(
                    logger,
                    "validate_db_correlation",
                    "Error consultando item en origen",
                    portal="origen",
                    id_viejo=row.layer_id,
                    exc=exc,
                )
                report_rows.append(
                    {
                        "id": row.id,
                        "client_code": row.client_code,
                        "item_type_code": row.item_type_code,
                        "service_name": row.service_name,
                        "layer_id": row.layer_id,
                        "service_url": row.service_url,
                        "origen_item_title": "",
                        "origen_item_url": "",
                        "resultado": RESULT_ERROR,
                        "detalle": str(exc),
                    }
                )
                continue

            if item is None:
                counts[RESULT_NOT_FOUND] += 1
                resultado = RESULT_NOT_FOUND
                origen_title = ""
                origen_url = ""
                detalle = "No existe o no es accesible en origen con esas credenciales"
            else:
                origen_title = item.title or ""
                origen_url = item.url or ""
                if _normalize_url(origen_url) == _normalize_url(row.service_url):
                    counts[RESULT_MATCH] += 1
                    resultado = RESULT_MATCH
                    detalle = "layer_id/service_url coinciden con itemId/url de origen"
                else:
                    counts[RESULT_MISMATCH] += 1
                    resultado = RESULT_MISMATCH
                    detalle = "La URL de origen no coincide con service_url guardado"

            logger.info(
                "id=%s client_code=%s layer_id=%s -> %s",
                row.id,
                row.client_code,
                row.layer_id,
                resultado,
            )
            report_rows.append(
                {
                    "id": row.id,
                    "client_code": row.client_code,
                    "item_type_code": row.item_type_code,
                    "service_name": row.service_name,
                    "layer_id": row.layer_id,
                    "service_url": row.service_url,
                    "origen_item_title": origen_title,
                    "origen_item_url": origen_url,
                    "resultado": resultado,
                    "detalle": detalle,
                }
            )

        with open(VALIDACION_CORRELACION, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=REPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(report_rows)

        summary = WorkflowSummary(
            script="validate_db_correlation",
            lines=[
                f" Filas evaluadas: {len(rows)}",
                f" MATCH (hipotesis confirmada): {counts[RESULT_MATCH]}",
                f" MISMATCH (hipotesis falsa): {counts[RESULT_MISMATCH]}",
                f" NOT_FOUND: {counts[RESULT_NOT_FOUND]}",
                f" EMPTY_LAYER_ID: {counts[RESULT_EMPTY_LAYER_ID]}",
                f" ERROR: {counts[RESULT_ERROR]}",
                f" Reporte: {VALIDACION_CORRELACION}",
            ],
            errors=counts[RESULT_ERROR] + counts[RESULT_MISMATCH],
            next_command="python scripts/generate_db_update.py --db-dsn",
            next_hint=(
                "Si predominan MATCH, use --join-key layer_id (default). "
                "Si predominan MISMATCH, revise antes de generar el SQL."
            ),
        )
        print_summary(summary, logger)
        return 0 if counts[RESULT_ERROR] == 0 else 1

    except Exception as exc:
        log_error_context(logger, "validate_db_correlation", "Validacion fallida", exc=exc)
        print_failure_summary("validate_db_correlation", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
