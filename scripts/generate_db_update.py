#!/usr/bin/env python3
"""Fase 2: genera un .sql de UPDATE (o, con --format yii, un migration de
Yii) para app.arcgis_upload a partir de mapeo_migracion.csv (filas EXITO)
y del estado actual de arcgis_upload (via DSN Postgres directo o CSV
exportado manualmente).

Este script es de SOLO LECTURA sobre la base de datos: nunca ejecuta
INSERT/UPDATE/DELETE. El archivo generado (.sql o .php) queda para
revision y ejecucion manual por el equipo de datos/DBA (ver
docs/DB_CORRELATION.md).

Clave de correlacion (--join-key):
- layer_id  (default): arcgis_upload.layer_id   == mapeo.ID_Viejo
- service_url:         arcgis_upload.service_url == mapeo.URL_Vieja

Ejecute primero scripts/validate_db_correlation.py para confirmar cual
clave aplica en su entorno antes de usar el resultado de este script.

Formato de salida (--format):
- sql (default): escribe update_arcgis_upload.sql (UPDATE envueltos en
  BEGIN;/COMMIT;), para ejecutar manualmente contra la BD.
- yii: en vez del .sql, escribe un migration de Yii (CDbMigration) listo
  para revisar y copiar a console/migrations/ en el proyecto fdsu, y
  correr con: php console/yiic migrate. Este toolkit no copia ni
  ejecuta ese archivo; solo lo deja en data/output/ para su revision.

Token de destino (access_token / username / token_expires_at):
El `access_token` guardado hoy en arcgis_upload fue emitido contra el
portal ORIGEN y no sirve sobre el Feature Service ya migrado a DESTINO.
Este script NO genera ni embebe un token nuevo (asi el archivo no es un
secreto). Por default pone access_token = '' y token_expires_at = ''
(cadena vacia: esas columnas son NOT NULL), y actualiza username a
DESTINO_USER. El token real lo escribe despues un comando aparte en el
proyecto fdsu. Use --no-token para no tocar esas columnas (solo
service_url + layer_id).
"""

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import (  # noqa: E402
    DATA_OUTPUT,
    MAPEO_MIGRACION,
    SIN_MATCH_ARCGIS_UPLOAD,
    UPDATE_ARCGIS_UPLOAD_SQL,
    get_env,
    load_config,
)
from migracion_esri.db_client import fetch_arcgis_upload_rows  # noqa: E402
from migracion_esri.logging_setup import log_error_context, setup_logging  # noqa: E402
from migracion_esri.workflow_ui import (  # noqa: E402
    WorkflowSummary,
    print_failure_summary,
    print_summary,
)
from migracion_esri.yii_migration import (  # noqa: E402
    build_migration_class_name,
    php_escape_double_quoted,
    render_cdb_migration,
)

ESTADO_EXITO = "EXITO"
YII_MIGRATION_DESCRIPTION = "update_arcgis_upload"

SIN_MATCH_COLUMNS = ["ID_Viejo", "URL_Vieja", "ID_Nuevo", "URL_Nueva", "Titulo", "Fecha"]


def _sql_quote(value: str) -> str:
    """Escapa un valor para usarlo entre comillas simples en SQL estandar."""
    return "'" + (value or "").replace("'", "''") + "'"


def _normalize(value: str) -> str:
    return (value or "").strip().rstrip("/").lower()


def _build_update_sql(
    row,
    mapeo_row: dict,
    null_token: bool = False,
    destino_user: str | None = None,
    trailing_semicolon: bool = True,
) -> str:
    """Arma el UPDATE app.arcgis_upload ... WHERE id = ... para una fila.

    Compartido por el renderer .sql y el renderer .php (Yii): mismo
    contenido/orden de columnas, solo cambia si lleva ';' al final (el
    .sql si; el que va embebido en un createCommand() de PHP, no).

    Con null_token, vacia el token de origen (access_token y
    token_expires_at = '', porque las columnas son NOT NULL) y deja
    username en la cuenta DESTINO. El token nuevo no se embebe aqui.
    """
    set_parts = [
        f"service_url = {_sql_quote(mapeo_row.get('URL_Nueva', ''))}",
        f"layer_id    = {_sql_quote(mapeo_row.get('ID_Nuevo', ''))}",
    ]
    if null_token:
        set_parts.append(f"username    = {_sql_quote(destino_user)}")
        set_parts.append(f"access_token = {_sql_quote('')}")
        set_parts.append(f"token_expires_at = {_sql_quote('')}")

    set_clause = ",\n    ".join(set_parts)
    suffix = ";" if trailing_semicolon else ""
    return f"UPDATE app.arcgis_upload\nSET {set_clause}\nWHERE id = {row.id}{suffix}"


def _build_update_sql_yii_lines(
    row,
    mapeo_row: dict,
    null_token: bool = False,
    destino_user: str | None = None,
) -> list[str]:
    """Arma el bloque SQL multilinea tal como se embebe en los migrations
    reales de fdsu: `UPDATE`/`SET`/`WHERE` en su propia linea (sangria con
    tabs), columnas sin alinear con espacios, y sin el prefijo de esquema
    `app.` (el `dbWrite` de Yii ya opera sobre ese esquema por default).

    Devuelve las lineas SIN escapar para PHP; quien las use debe pasarlas
    por php_escape_double_quoted() antes de insertarlas en un string "...".
    """
    set_parts = [
        f"service_url = {_sql_quote(mapeo_row.get('URL_Nueva', ''))}",
        f"layer_id = {_sql_quote(mapeo_row.get('ID_Nuevo', ''))}",
    ]
    if null_token:
        set_parts.append(f"username = {_sql_quote(destino_user)}")
        set_parts.append(f"access_token = {_sql_quote('')}")
        set_parts.append(f"token_expires_at = {_sql_quote('')}")

    lines = ["\t\tUPDATE arcgis_upload", "\t\tSET"]
    last = len(set_parts) - 1
    for i, part in enumerate(set_parts):
        comma = "," if i < last else ""
        lines.append(f"\t\t\t{part}{comma}")
    lines.append("\t\tWHERE")
    lines.append(f"\t\t\tid = {row.id}")
    return lines


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


def _render_sql(
    join_key: str,
    updates: list[tuple],
    sin_match: list[dict],
    null_token: bool,
    destino_user: str | None,
    timestamp: str,
) -> str:
    lines = [
        "-- Generado por scripts/generate_db_update.py",
        f"-- Fecha: {timestamp}",
        f"-- Clave de correlacion: {join_key}",
        f"-- UPDATEs generados: {len(updates)}",
        f"-- Filas EXITO sin match en arcgis_upload: {len(sin_match)}",
        "-- REVISAR Y EJECUTAR MANUALMENTE. Este script no modifica la base de datos.",
    ]
    if null_token:
        lines.append(
            f"-- Vacia access_token y token_expires_at ('') y pone username={destino_user}."
        )
        lines.append(
            "-- El token de DESTINO no va en este archivo: lo escribe despues un comando en fdsu."
        )
    lines.extend(["BEGIN;", ""])

    for row, mapeo_row in updates:
        lines.append(
            f"-- {mapeo_row.get('Titulo', '')} | client_code={row.client_code} | "
            f"item_type_code={row.item_type_code} | id={row.id}"
        )
        lines.append(_build_update_sql(row, mapeo_row, null_token, destino_user))
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
    return "\n".join(lines) + "\n"


def _render_yii_migration(
    class_name: str,
    join_key: str,
    updates: list[tuple],
    sin_match: list[dict],
    null_token: bool,
    destino_user: str | None,
    timestamp: str,
) -> str:
    docblock_lines = [
        "Migration: Update app.arcgis_upload after ArcGIS portal migration.",
        "",
        "Generado por scripts/generate_db_update.py (migracion_esri).",
        f"Fecha: {timestamp}",
        f"Clave de correlacion: {join_key}",
        f"UPDATEs generados: {len(updates)}",
        f"Filas EXITO sin match en arcgis_upload: {len(sin_match)}",
    ]
    if null_token:
        docblock_lines.append(
            f"Vacia access_token y token_expires_at ('') y pone username={destino_user}."
        )
        docblock_lines.append(
            "El token de DESTINO no va en este archivo: lo escribe despues un comando en fdsu."
        )
    docblock_lines.append("")
    docblock_lines.append(
        "REVISAR antes de copiar a console/migrations/ en el proyecto fdsu y"
    )
    docblock_lines.append("ejecutar manualmente con: php console/yiic migrate")

    total = len(updates)
    up_lines = [f"        $total = {total};", "        $updated = 0;", ""]

    for row, mapeo_row in updates:
        sql_lines = _build_update_sql_yii_lines(row, mapeo_row, null_token, destino_user)
        up_lines.append(
            f"        // {mapeo_row.get('Titulo', '')} | client_code={row.client_code} | "
            f"item_type_code={row.item_type_code} | id={row.id}"
        )
        up_lines.append('        Yii::app()->dbWrite->createCommand("')
        up_lines.extend(php_escape_double_quoted(line) for line in sql_lines)
        up_lines.append('\t")')
        up_lines.append("\t->execute();")
        up_lines.append("        $updated++;")
        up_lines.append(
            "        echo date('Y-m-d H:i:s') . \"\\n\" . \"Update {$updated}/{$total} (id="
            + str(row.id)
            + ")\" . \"\\n\\n\";"
        )
        up_lines.append("")

    if sin_match:
        up_lines.append(
            "        // ADVERTENCIA: filas EXITO del mapeo sin fila correspondiente en arcgis_upload:"
        )
        for mapeo_row in sin_match:
            up_lines.append(
                f"        //   ID_Viejo={mapeo_row.get('ID_Viejo')} Titulo={mapeo_row.get('Titulo')} "
                f"URL_Vieja={mapeo_row.get('URL_Vieja')}"
            )
        up_lines.append("")

    up_lines.append("        (new CacheDbSchema)->invalidate(['arcgis_upload']);")
    up_lines.append("")
    up_lines.append("        return true;")
    up_body = "\n".join(up_lines)

    down_body = (
        "        echo \""
        + class_name
        + " no soporta rollback (actualiza access_token/service_url/layer_id).\\n\";\n"
        "        return false;"
    )

    return render_cdb_migration(class_name, docblock_lines, up_body, down_body)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera update_arcgis_upload.sql (o un migration Yii) a partir de "
        "mapeo_migracion.csv (solo lectura en BD)"
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
        "--format",
        choices=["sql", "yii"],
        default="sql",
        help="sql (default): genera update_arcgis_upload.sql. "
        "yii: genera SOLO un migration CDbMigration (.php) en vez del .sql, "
        "listo para revisar y copiar a console/migrations/ en fdsu.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ruta de salida (default: data/output/update_arcgis_upload.sql, o "
        "data/output/m{timestamp}_update_arcgis_upload.php con --format yii)",
    )
    parser.add_argument(
        "--no-token",
        action="store_true",
        help="No tocar access_token/username/token_expires_at (solo service_url + layer_id)",
    )
    args = parser.parse_args()

    load_config()
    logger = setup_logging("generate_db_update")
    logger.info(
        "=== INICIO generate_db_update (join_key=%s, format=%s, token=%s) ===",
        args.join_key,
        args.format,
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
                next_hint="Ejecute o complete la migracion antes de generar el resultado",
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

        null_token = not args.no_token and bool(updates)
        destino_user = get_env("DESTINO_USER") if null_token else None
        if null_token:
            logger.info(
                "access_token y token_expires_at quedan en ''; username=%s. "
                "El token de destino lo escribe despues un comando en fdsu.",
                destino_user,
            )

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        if args.format == "yii":
            class_name = build_migration_class_name(YII_MIGRATION_DESCRIPTION, when=time.localtime())
            output_path = args.output or (DATA_OUTPUT / f"{class_name}.php")
            content = _render_yii_migration(
                class_name,
                args.join_key,
                updates,
                sin_match,
                null_token,
                destino_user,
                timestamp,
            )
        else:
            output_path = args.output or UPDATE_ARCGIS_UPLOAD_SQL
            content = _render_sql(
                args.join_key,
                updates,
                sin_match,
                null_token,
                destino_user,
                timestamp,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="\n", encoding="utf-8") as f:
            f.write(content)

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
            f" Formato: {args.format}",
            f" Archivo: {output_path}",
        ]
        if sin_match:
            summary_lines.append(f" Sin-match CSV: {SIN_MATCH_ARCGIS_UPLOAD}")
        if null_token:
            summary_lines.append(
                f" access_token y token_expires_at = ''; username = {destino_user}"
            )
            summary_lines.append(
                " El token de DESTINO no va en este archivo: lo escribe despues un comando en fdsu"
            )

        if args.format == "yii":
            next_command = (
                f"(externo) revisar {output_path.name}, copiarlo a console/migrations/ en fdsu "
                "y ejecutar: php console/yiic migrate"
            )
            next_hint = (
                "Este tool no copia ni ejecuta el migration. Despues, el comando PHP de fdsu "
                "debe escribir el access_token de DESTINO."
            )
        else:
            next_command = "(externo) revisar y ejecutar el .sql manualmente contra la BD"
            next_hint = (
                "Este tool no ejecuta el UPDATE. Despues, el comando PHP de fdsu "
                "debe escribir el access_token de DESTINO."
            )

        summary = WorkflowSummary(
            script="generate_db_update",
            lines=summary_lines,
            errors=0,
            next_command=next_command,
            next_hint=next_hint,
        )
        print_summary(summary, logger)
        return 0

    except Exception as exc:
        log_error_context(logger, "generate_db_update", "Generacion de resultado fallida", exc=exc)
        print_failure_summary("generate_db_update", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
