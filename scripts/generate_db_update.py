#!/usr/bin/env python3
"""Fase 2: genera un .sql de UPDATE para app.arcgis_upload a partir de
mapeo_migracion.csv (filas EXITO) y del estado actual de arcgis_upload
(via DSN Postgres directo o CSV exportado manualmente).

Este script es de SOLO LECTURA sobre la base de datos: nunca ejecuta
INSERT/UPDATE/DELETE. El .sql generado queda para revision y ejecucion
manual por el equipo de datos/DBA (ver docs/DB_CORRELATION.md).

Clave de correlacion (--join-key):
- layer_id  (default): arcgis_upload.layer_id   == mapeo.ID_Viejo
- service_url:         arcgis_upload.service_url == mapeo.URL_Vieja

Ejecute primero scripts/validate_db_correlation.py para confirmar cual
clave aplica en su entorno antes de usar el resultado de este script.

Token de destino (access_token / username / token_expires_at):
El `access_token` guardado hoy en arcgis_upload fue emitido contra el
portal ORIGEN; no sirve para operar sobre el Feature Service ya migrado
a DESTINO. Por default este script pide UN token nuevo (via REST
generateToken) para la cuenta DESTINO_USER/.env y lo incluye en cada
UPDATE junto con username=DESTINO_USER. Use --no-token para generar el
SQL sin tocar esas columnas (comportamiento anterior).

ADVERTENCIA DE SEGURIDAD: el .sql resultante queda con un token valido
embebido -> tratelo como un secreto (no lo comparta ni lo deje en
repos/tickets, borrelo despues de aplicarlo). El token expira segun
--token-expiration-minutes (default 60): aplique el .sql antes de ese
plazo o el token ya estara vencido.
"""

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.arcgis_token import TokenGenerationError, generate_destino_token  # noqa: E402
from migracion_esri.config import (  # noqa: E402
    MAPEO_MIGRACION,
    SIN_MATCH_ARCGIS_UPLOAD,
    UPDATE_ARCGIS_UPLOAD_SQL,
    get_env,
    get_token_expiration_minutes,
    load_config,
)
from migracion_esri.db_client import fetch_arcgis_upload_rows  # noqa: E402
from migracion_esri.logging_setup import log_error_context, setup_logging  # noqa: E402
from migracion_esri.workflow_ui import (  # noqa: E402
    WorkflowSummary,
    print_failure_summary,
    print_summary,
)

ESTADO_EXITO = "EXITO"

SIN_MATCH_COLUMNS = ["ID_Viejo", "URL_Vieja", "ID_Nuevo", "URL_Nueva", "Titulo", "Fecha"]


def _sql_quote(value: str) -> str:
    """Escapa un valor para usarlo entre comillas simples en SQL estandar."""
    return "'" + (value or "").replace("'", "''") + "'"


def _normalize(value: str) -> str:
    return (value or "").strip().rstrip("/").lower()


def load_mapeo_exitos(mapeo_path: Path) -> dict[str, dict]:
    """Lee mapeo_migracion.csv y devuelve solo filas EXITO, dedupe por ID_Viejo
    (si el mismo item se reintento varias veces, se queda la ultima EXITO)."""
    if not mapeo_path.exists():
        raise FileNotFoundError(f"No existe {mapeo_path}. Ejecute primero scripts/migrate.py")

    exitos: dict[str, dict] = {}
    with open(mapeo_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("Estado") or "").strip().upper() != ESTADO_EXITO:
                continue
            id_viejo = (row.get("ID_Viejo") or "").strip()
            if not id_viejo:
                continue
            exitos[id_viejo] = row  # el ultimo EXITO para ese id_viejo gana
    return exitos


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera update_arcgis_upload.sql a partir de mapeo_migracion.csv (solo lectura en BD)"
    )
    parser.add_argument("--mapeo", type=Path, default=MAPEO_MIGRACION, help="CSV de mapeo (default mapeo_migracion.csv)")
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
        "--join-key",
        choices=["layer_id", "service_url"],
        default="layer_id",
        help="Clave de correlacion a usar (default layer_id, confirmar con validate_db_correlation.py)",
    )
    parser.add_argument(
        "--only-system-account",
        action="store_true",
        help="Filtrar solo filas con is_system_account = true (requiere --db-dsn)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=UPDATE_ARCGIS_UPLOAD_SQL,
        help="Ruta de salida del .sql generado",
    )
    parser.add_argument(
        "--no-token",
        action="store_true",
        help="No generar/incluir access_token nuevo (solo service_url + layer_id, comportamiento anterior)",
    )
    parser.add_argument(
        "--token-expiration-minutes",
        type=int,
        default=None,
        help="Expiracion del token nuevo en minutos (default: TOKEN_EXPIRATION_MINUTES en .env, o 60)",
    )
    args = parser.parse_args()

    load_config()
    logger = setup_logging("generate_db_update")
    logger.info(
        "=== INICIO generate_db_update (join_key=%s, token=%s) ===",
        args.join_key,
        not args.no_token,
    )

    try:
        exitos = load_mapeo_exitos(args.mapeo)
        logger.info("Filas EXITO en mapeo: %d", len(exitos))

        if not exitos:
            summary = WorkflowSummary(
                script="generate_db_update",
                lines=[" No hay filas EXITO en el mapeo; nada que generar."],
                next_command="python scripts/migrate.py",
                next_hint="Ejecute o complete la migracion antes de generar el SQL",
            )
            print_summary(summary, logger)
            return 0

        # Para join-key=service_url, se indexa por URL_Vieja normalizada.
        exitos_by_key: dict[str, dict] = {}
        for id_viejo, row in exitos.items():
            key = id_viejo if args.join_key == "layer_id" else _normalize(row.get("URL_Vieja", ""))
            if key:
                exitos_by_key[key] = row

        arcgis_rows = fetch_arcgis_upload_rows(
            db_dsn=args.db_dsn,
            csv_path=args.arcgis_upload_csv,
            only_system_account=args.only_system_account,
        )
        logger.info("Filas arcgis_upload leidas: %d", len(arcgis_rows))

        matched_keys: set[str] = set()
        updates: list[tuple] = []  # (arcgis_row, mapeo_row)

        for row in arcgis_rows:
            key = row.layer_id if args.join_key == "layer_id" else _normalize(row.service_url)
            if not key:
                continue
            mapeo_row = exitos_by_key.get(key)
            if mapeo_row is None:
                continue
            matched_keys.add(key)
            updates.append((row, mapeo_row))
            logger.info(
                "Match arcgis_upload.id=%s client_code=%s <- mapeo ID_Viejo=%s",
                row.id,
                row.client_code,
                mapeo_row.get("ID_Viejo"),
            )

        sin_match = [row for key, row in exitos_by_key.items() if key not in matched_keys]

        token = None
        token_expires_at = None  # epoch Unix en segundos (int), no se quotea en el SQL
        token_expires_readable = None  # solo para logs/comentarios, formato legible UTC
        destino_user = None
        if not args.no_token and updates:
            destino_url = get_env("DESTINO_URL")
            destino_user = get_env("DESTINO_USER")
            destino_pass = get_env("DESTINO_PASS")
            expiration_minutes = (
                args.token_expiration_minutes
                if args.token_expiration_minutes is not None
                else get_token_expiration_minutes()
            )
            logger.info(
                "Generando token para DESTINO (user=%s, expiration=%d min)...",
                destino_user,
                expiration_minutes,
            )
            try:
                token, token_expires_at = generate_destino_token(
                    destino_url, destino_user, destino_pass, expiration_minutes
                )
            except TokenGenerationError as exc:
                raise RuntimeError(f"No se pudo generar el token de destino: {exc}") from exc
            token_expires_readable = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(token_expires_at))
            logger.info(
                "Token generado, expira (epoch): %s (UTC: %s)", token_expires_at, token_expires_readable
            )

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "-- Generado por scripts/generate_db_update.py",
            f"-- Fecha: {timestamp}",
            f"-- Clave de correlacion: {args.join_key}",
            f"-- UPDATEs generados: {len(updates)}",
            f"-- Filas EXITO sin match en arcgis_upload: {len(sin_match)}",
            "-- REVISAR Y EJECUTAR MANUALMENTE. Este script no modifica la base de datos.",
        ]
        if token:
            lines.append(
                f"-- Incluye access_token nuevo para DESTINO_USER={destino_user}, "
                f"expira (epoch): {token_expires_at} (UTC: {token_expires_readable})"
            )
            lines.append(
                "-- SEGURIDAD: este archivo contiene un token valido -- tratelo como secreto "
                "y aplique antes de la expiracion indicada arriba."
            )
        lines.extend(["BEGIN;", ""])
        for row, mapeo_row in updates:
            lines.append(
                f"-- {mapeo_row.get('Titulo', '')} | client_code={row.client_code} | "
                f"item_type_code={row.item_type_code} | id={row.id}"
            )
            if token:
                lines.append(
                    "UPDATE app.arcgis_upload\n"
                    f"SET service_url = {_sql_quote(mapeo_row.get('URL_Nueva', ''))},\n"
                    f"    layer_id    = {_sql_quote(mapeo_row.get('ID_Nuevo', ''))},\n"
                    f"    username    = {_sql_quote(destino_user)},\n"
                    f"    access_token = {_sql_quote(token)},\n"
                    f"    token_expires_at = {int(token_expires_at)}\n"
                    f"WHERE id = {row.id};"
                )
            else:
                lines.append(
                    "UPDATE app.arcgis_upload\n"
                    f"SET service_url = {_sql_quote(mapeo_row.get('URL_Nueva', ''))},\n"
                    f"    layer_id    = {_sql_quote(mapeo_row.get('ID_Nuevo', ''))}\n"
                    f"WHERE id = {row.id};"
                )
            lines.append("")

        if sin_match:
            lines.append("-- ADVERTENCIA: filas EXITO del mapeo sin fila correspondiente en arcgis_upload:")
            for mapeo_row in sin_match:
                lines.append(
                    f"--   ID_Viejo={mapeo_row.get('ID_Viejo')} Titulo={mapeo_row.get('Titulo')} "
                    f"URL_Vieja={mapeo_row.get('URL_Vieja')}"
                )
            lines.append("")

        lines.append("COMMIT;")

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", newline="\n", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        if sin_match:
            with open(SIN_MATCH_ARCGIS_UPLOAD, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=SIN_MATCH_COLUMNS)
                writer.writeheader()
                for mapeo_row in sin_match:
                    writer.writerow({col: mapeo_row.get(col, "") for col in SIN_MATCH_COLUMNS})

        summary_lines = [
            f" Filas EXITO en mapeo: {len(exitos)}",
            f" UPDATEs generados: {len(updates)}",
            f" Sin match en arcgis_upload: {len(sin_match)}",
            f" SQL: {args.output}",
        ]
        if sin_match:
            summary_lines.append(f" Sin-match CSV: {SIN_MATCH_ARCGIS_UPLOAD}")
        if token:
            summary_lines.append(f" Token DESTINO generado para: {destino_user}")
            summary_lines.append(
                f" Token expira (epoch): {token_expires_at} (UTC: {token_expires_readable})"
                " -- aplique el .sql antes de esa hora"
            )

        summary = WorkflowSummary(
            script="generate_db_update",
            lines=summary_lines,
            errors=0,
            next_command="(externo) revisar y ejecutar el .sql manualmente contra la BD",
            next_hint="Este tool no ejecuta el UPDATE; entregue el .sql al equipo de datos/DBA (es un secreto: trate el .sql con cuidado)",
        )
        print_summary(summary, logger)
        return 0

    except Exception as exc:
        log_error_context(logger, "generate_db_update", "Generacion de SQL fallida", exc=exc)
        print_failure_summary("generate_db_update", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
