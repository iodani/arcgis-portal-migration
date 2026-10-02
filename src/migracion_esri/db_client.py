"""Acceso de SOLO LECTURA a app.arcgis_upload (DSN Postgres directo o CSV manual).

Este modulo nunca ejecuta INSERT/UPDATE/DELETE. Lo usan:
- scripts/validate_db_correlation.py (Fase 0: valida la clave de correlacion)
- scripts/generate_db_update.py (Fase 2: genera el .sql de UPDATE para revision manual)
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from migracion_esri.config import get_pg_dsn

ARCGIS_UPLOAD_CSV_COLUMNS = [
    "id",
    "client_code",
    "service_name",
    "item_type_code",
    "layer_id",
    "service_url",
]


@dataclass
class ArcgisUploadRow:
    id: int
    client_code: str
    service_name: str
    item_type_code: str
    layer_id: str
    service_url: str


def fetch_arcgis_upload_rows(
    *,
    db_dsn: bool = False,
    csv_path: Path | None = None,
    only_system_account: bool = False,
) -> list[ArcgisUploadRow]:
    """Obtiene filas de arcgis_upload desde Postgres (--db-dsn) o desde un CSV exportado."""
    if db_dsn and csv_path:
        raise ValueError("Use --db-dsn o --arcgis-upload-csv, no ambos a la vez")
    if not db_dsn and not csv_path:
        raise ValueError("Debe indicar --db-dsn o --arcgis-upload-csv")

    if csv_path:
        return _fetch_from_csv(csv_path)
    return _fetch_from_db(only_system_account=only_system_account)


def _fetch_from_csv(csv_path: Path) -> list[ArcgisUploadRow]:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"No existe {csv_path}. Exporte app.arcgis_upload con columnas: "
            + ", ".join(ARCGIS_UPLOAD_CSV_COLUMNS)
        )
    rows: list[ArcgisUploadRow] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        missing = set(ARCGIS_UPLOAD_CSV_COLUMNS) - fieldnames
        if missing:
            raise ValueError(
                f"Columnas faltantes en {csv_path}: {', '.join(sorted(missing))}"
            )
        for raw in reader:
            rows.append(
                ArcgisUploadRow(
                    id=int(raw["id"]),
                    client_code=(raw.get("client_code") or "").strip(),
                    service_name=(raw.get("service_name") or "").strip(),
                    item_type_code=(raw.get("item_type_code") or "").strip(),
                    layer_id=(raw.get("layer_id") or "").strip(),
                    service_url=(raw.get("service_url") or "").strip(),
                )
            )
    return rows


def _fetch_from_db(*, only_system_account: bool = False) -> list[ArcgisUploadRow]:
    import psycopg2
    import psycopg2.extras

    dsn, schema = get_pg_dsn()
    sql = (
        f"SELECT id, client_code, service_name, item_type_code, layer_id, service_url "
        f"FROM {schema}.arcgis_upload"
    )
    if only_system_account:
        sql += " WHERE is_system_account = true"
    sql += " ORDER BY client_code, item_type_code"

    rows: list[ArcgisUploadRow] = []
    conn = psycopg2.connect(dsn)
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            for record in cur.fetchall():
                rows.append(
                    ArcgisUploadRow(
                        id=record["id"],
                        client_code=(record["client_code"] or "").strip(),
                        service_name=(record["service_name"] or "").strip(),
                        item_type_code=(record["item_type_code"] or "").strip(),
                        layer_id=(record["layer_id"] or "").strip(),
                        service_url=(record["service_url"] or "").strip(),
                    )
                )
    finally:
        conn.close()
    return rows
