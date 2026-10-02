#!/usr/bin/env python3
"""Prepara data/input/inventario_migracion.csv desde el audit del origen.

Modo normal (sin flags): copia TODO el inventario auditado tal cual, para
que el usuario lo cure a mano (quite filas que no quiera migrar).

Modo --db-dsn / --arcgis-upload-csv: filtra automaticamente el inventario
auditado para quedarse SOLO con los items que estan registrados en
app.arcgis_upload (correlacionando por layer_id o service_url). Si algun
item de arcgis_upload no aparece en el audit (por ejemplo, por ser privado
de una cuenta que el audit no vio), intenta resolverlo con un lookup
directo al portal origen antes de darlo por perdido.
"""

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import (  # noqa: E402
    DATA_INPUT,
    INVENTARIO_CARPETAS,
    SIN_MATCH_INVENTARIO_DB,
    load_config,
)
from migracion_esri.db_client import ArcgisUploadRow, fetch_arcgis_upload_rows  # noqa: E402
from migracion_esri.drivers.registry import get_driver_name, get_fase  # noqa: E402
from migracion_esri.folders import build_folder_map, resolve_folder_name  # noqa: E402
from migracion_esri.gis_client import validate_connections  # noqa: E402
from migracion_esri.logging_setup import log_error_context, setup_logging  # noqa: E402
from migracion_esri.workflow_ui import (  # noqa: E402
    WorkflowSummary,
    print_failure_summary,
    print_summary,
)

OUTPUT_COLUMNS = [
    "Titulo",
    "ID_Viejo",
    "URL_Vieja",
    "Carpeta_Origen",
    "Type",
    "Fase",
    "Driver",
]
LEGACY_COLUMNS = ["Titulo", "ID_Viejo", "URL_Vieja", "Carpeta_Origen"]

SIN_MATCH_DB_COLUMNS = [
    "id",
    "client_code",
    "service_name",
    "item_type_code",
    "layer_id",
    "service_url",
]


def _normalize(value: str) -> str:
    return (value or "").strip().rstrip("/").lower()


def _load_audit_df() -> pd.DataFrame:
    if not INVENTARIO_CARPETAS.exists():
        raise FileNotFoundError(
            f"No existe {INVENTARIO_CARPETAS}. Ejecute primero: python scripts/audit.py"
        )
    df = pd.read_csv(INVENTARIO_CARPETAS)
    if "Type" not in df.columns:
        missing = set(LEGACY_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(
                f"Columnas faltantes en inventario auditado: {', '.join(sorted(missing))}"
            )
        df = df[LEGACY_COLUMNS].copy()
        df["Type"] = "Feature Service"
        df["Fase"] = 1
        df["Driver"] = "feature_service"
        return df

    missing = set(OUTPUT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"Columnas faltantes en inventario auditado: {', '.join(sorted(missing))}"
        )
    return df


def _filter_by_db(
    df: pd.DataFrame, arcgis_rows: list[ArcgisUploadRow], join_key: str
) -> tuple[pd.DataFrame, list[ArcgisUploadRow]]:
    """Filtra df (inventario auditado) a solo las filas presentes en
    arcgis_upload. Devuelve (filas_encontradas, filas_de_arcgis_upload_sin_match)."""
    df = df.copy()
    if join_key == "layer_id":
        df["_key"] = df["ID_Viejo"].astype(str).str.strip()
    else:
        df["_key"] = df["URL_Vieja"].fillna("").map(_normalize)

    wanted: dict[str, ArcgisUploadRow] = {}
    for row in arcgis_rows:
        key = row.layer_id if join_key == "layer_id" else _normalize(row.service_url)
        if key:
            wanted[key] = row

    matched_mask = df["_key"].isin(wanted.keys())
    matched_df = df[matched_mask][OUTPUT_COLUMNS].copy()
    found_keys = set(df.loc[matched_mask, "_key"])

    missing = [row for key, row in wanted.items() if key not in found_keys]
    return matched_df, missing


def _resolve_missing(
    missing: list[ArcgisUploadRow], logger
) -> tuple[pd.DataFrame, list[ArcgisUploadRow]]:
    """Intenta resolver filas de arcgis_upload que no aparecieron en el audit,
    buscando el item directamente en el portal origen por layer_id."""
    if not missing:
        return pd.DataFrame(columns=OUTPUT_COLUMNS), []

    logger.info(
        "Resolviendo %d filas de arcgis_upload no encontradas en el audit "
        "con lookup directo al portal origen...",
        len(missing),
    )
    gis_origen, _, _, _ = validate_connections(logger)
    folder_map = build_folder_map(gis_origen)

    resolved_rows = []
    unresolved: list[ArcgisUploadRow] = []
    for row in missing:
        if not row.layer_id:
            unresolved.append(row)
            continue
        try:
            item = gis_origen.content.get(row.layer_id)
        except Exception as exc:
            logger.warning("Error buscando layer_id=%s en origen: %s", row.layer_id, exc)
            unresolved.append(row)
            continue
        if item is None:
            unresolved.append(row)
            continue
        item_type = item.type or "Unknown"
        resolved_rows.append(
            {
                "Titulo": item.title,
                "ID_Viejo": item.id,
                "URL_Vieja": item.url or "",
                "Carpeta_Origen": resolve_folder_name(gis_origen, item.ownerFolder, folder_map),
                "Type": item_type,
                "Fase": get_fase(item_type),
                "Driver": get_driver_name(item_type),
            }
        )
        logger.info("Resuelto por lookup directo: %s (layer_id=%s)", item.title, row.layer_id)

    return pd.DataFrame(resolved_rows, columns=OUTPUT_COLUMNS), unresolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preparar inventario de migracion desde auditoria"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobrescribir data/input/inventario_migracion.csv si ya existe",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--db-dsn",
        action="store_true",
        help="Filtrar automaticamente usando app.arcgis_upload via DSN Postgres (PGDSN en .env)",
    )
    source.add_argument(
        "--arcgis-upload-csv",
        type=Path,
        default=None,
        help="Filtrar automaticamente usando un CSV exportado manualmente de arcgis_upload",
    )
    parser.add_argument(
        "--join-key",
        choices=["layer_id", "service_url"],
        default="layer_id",
        help="Clave de correlacion con --db-dsn/--arcgis-upload-csv (default layer_id)",
    )
    parser.add_argument(
        "--only-system-account",
        action="store_true",
        help="Filtrar solo filas is_system_account = true (requiere --db-dsn)",
    )
    args = parser.parse_args()
    from_db = bool(args.db_dsn or args.arcgis_upload_csv)

    load_config()
    logger = setup_logging("prepare")
    logger.info("=== INICIO prepare (from_db=%s) ===", from_db)

    try:
        if DATA_INPUT.exists() and not args.force:
            raise FileExistsError(
                f"Ya existe {DATA_INPUT}. Edite el archivo, use --force, o borrelo antes de regenerar."
            )

        df = _load_audit_df()

        if from_db:
            arcgis_rows = fetch_arcgis_upload_rows(
                db_dsn=args.db_dsn,
                csv_path=args.arcgis_upload_csv,
                only_system_account=args.only_system_account,
            )
            logger.info("Filas en arcgis_upload a correlacionar: %d", len(arcgis_rows))

            matched_df, missing = _filter_by_db(df, arcgis_rows, args.join_key)
            resolved_df, unresolved = _resolve_missing(missing, logger)

            out = pd.concat([matched_df, resolved_df], ignore_index=True)
            if not out.empty:
                out = out.drop_duplicates(subset=["ID_Viejo"])

            if unresolved:
                SIN_MATCH_INVENTARIO_DB.parent.mkdir(parents=True, exist_ok=True)
                with open(SIN_MATCH_INVENTARIO_DB, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=SIN_MATCH_DB_COLUMNS)
                    writer.writeheader()
                    for row in unresolved:
                        writer.writerow(
                            {
                                "id": row.id,
                                "client_code": row.client_code,
                                "service_name": row.service_name,
                                "item_type_code": row.item_type_code,
                                "layer_id": row.layer_id,
                                "service_url": row.service_url,
                            }
                        )
                logger.warning(
                    "%d filas de arcgis_upload no se pudieron resolver, ver %s",
                    len(unresolved),
                    SIN_MATCH_INVENTARIO_DB,
                )

            lines = [
                f" Filas en arcgis_upload: {len(arcgis_rows)}",
                f" Encontradas en audit: {len(matched_df)}",
                f" Resueltas por lookup directo en origen: {len(resolved_df)}",
                f" Sin resolver: {len(unresolved)}",
                f" Total en inventario de migracion: {len(out)}",
                f" Destino: {DATA_INPUT}",
            ]
            if unresolved:
                lines.append(f" Revisar sin resolver: {SIN_MATCH_INVENTARIO_DB}")
            next_hint = (
                "Inventario ya filtrado por BD; revise el CSV (puede seguir "
                "editandolo) y ejecute la migracion masiva"
            )
        else:
            out = df[OUTPUT_COLUMNS].copy()
            lines = [
                f" Filas copiadas: {len(out)}",
                f" Origen:  {INVENTARIO_CARPETAS}",
                f" Destino: {DATA_INPUT}",
                " Edite el CSV y elimine filas que NO desee migrar",
            ]
            next_hint = "Tras curar el inventario, ejecutar migracion masiva"

        out.to_csv(DATA_INPUT, index=False, encoding="utf-8")

        summary = WorkflowSummary(
            script="prepare",
            lines=lines,
            next_command="python scripts/migrate.py",
            next_hint=next_hint,
        )
        print_summary(summary, logger)
        return 0

    except Exception as exc:
        log_error_context(logger, "prepare", "Preparacion fallida", exc=exc)
        print_failure_summary("prepare", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
