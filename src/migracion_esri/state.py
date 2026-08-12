import csv
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from migracion_esri.config import MAPEO_MIGRACION, STATE_DB, ensure_dirs

STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

MAPEO_HEADERS = [
    "ID_Viejo",
    "URL_Vieja",
    "ID_Nuevo",
    "URL_Nueva",
    "Titulo",
    "Carpeta_Origen",
    "Estado",
    "Error",
    "Fecha",
]


@dataclass
class MigrationItem:
    id_viejo: str
    titulo: str
    url_vieja: str
    carpeta_origen: str
    id_nuevo: str = ""
    url_nueva: str = ""
    estado: str = STATUS_PENDING
    error: str = ""
    updated_at: str = ""


class MigrationState:
    def __init__(self, db_path: Path = STATE_DB):
        ensure_dirs()
        self.db_path = db_path
        self._init_db()
        self._ensure_mapeo_csv()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS migration_items (
                    id_viejo TEXT PRIMARY KEY,
                    titulo TEXT NOT NULL,
                    url_vieja TEXT,
                    carpeta_origen TEXT,
                    id_nuevo TEXT,
                    url_nueva TEXT,
                    estado TEXT NOT NULL,
                    error TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _ensure_mapeo_csv(self) -> None:
        if not MAPEO_MIGRACION.exists():
            with open(MAPEO_MIGRACION, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(MAPEO_HEADERS)

    def upsert_from_inventory(self, items: list[MigrationItem]) -> None:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO migration_items (
                        id_viejo, titulo, url_vieja, carpeta_origen,
                        id_nuevo, url_nueva, estado, error, updated_at
                    ) VALUES (?, ?, ?, ?, '', '', ?, '', ?)
                    """,
                    (
                        item.id_viejo,
                        item.titulo,
                        item.url_vieja,
                        item.carpeta_origen,
                        STATUS_PENDING,
                        now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE migration_items
                    SET titulo = ?, url_vieja = ?, carpeta_origen = ?, updated_at = ?
                    WHERE id_viejo = ? AND estado != ?
                    """,
                    (
                        item.titulo,
                        item.url_vieja,
                        item.carpeta_origen,
                        now,
                        item.id_viejo,
                        STATUS_SUCCESS,
                    ),
                )

    def get_items_to_process(self, retry_errors: bool = False) -> list[MigrationItem]:
        if retry_errors:
            statuses = (STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_ERROR)
        else:
            statuses = (STATUS_PENDING, STATUS_IN_PROGRESS)

        placeholders = ",".join("?" for _ in statuses)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM migration_items
                WHERE estado IN ({placeholders})
                ORDER BY titulo
                """,
                statuses,
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def set_in_progress(self, id_viejo: str) -> None:
        self._update_item(id_viejo, estado=STATUS_IN_PROGRESS, error="")

    def set_success(self, id_viejo: str, id_nuevo: str, url_nueva: str) -> None:
        item = self.get_item(id_viejo)
        self._update_item(
            id_viejo,
            estado=STATUS_SUCCESS,
            id_nuevo=id_nuevo,
            url_nueva=url_nueva,
            error="",
        )
        self._append_mapeo_csv(item, id_nuevo, url_nueva, "EXITO", "")

    def set_error(self, id_viejo: str, error: str) -> None:
        item = self.get_item(id_viejo)
        self._update_item(id_viejo, estado=STATUS_ERROR, error=error)
        self._append_mapeo_csv(item, "", "", "ERROR", error)

    def get_item(self, id_viejo: str) -> MigrationItem:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM migration_items WHERE id_viejo = ?", (id_viejo,)
            ).fetchone()
        if row is None:
            raise KeyError(id_viejo)
        return self._row_to_item(row)

    def _update_item(
        self,
        id_viejo: str,
        *,
        estado: str | None = None,
        id_nuevo: str | None = None,
        url_nueva: str | None = None,
        error: str | None = None,
    ) -> None:
        fields = []
        values = []
        if estado is not None:
            fields.append("estado = ?")
            values.append(estado)
        if id_nuevo is not None:
            fields.append("id_nuevo = ?")
            values.append(id_nuevo)
        if url_nueva is not None:
            fields.append("url_nueva = ?")
            values.append(url_nueva)
        if error is not None:
            fields.append("error = ?")
            values.append(error)
        fields.append("updated_at = ?")
        values.append(time.strftime("%Y-%m-%d %H:%M:%S"))
        values.append(id_viejo)

        with self._connect() as conn:
            conn.execute(
                f"UPDATE migration_items SET {', '.join(fields)} WHERE id_viejo = ?",
                values,
            )

    def _append_mapeo_csv(
        self,
        item: MigrationItem,
        id_nuevo: str,
        url_nueva: str,
        estado: str,
        error: str,
    ) -> None:
        with open(MAPEO_MIGRACION, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [
                    item.id_viejo,
                    item.url_vieja,
                    id_nuevo,
                    url_nueva,
                    item.titulo,
                    item.carpeta_origen,
                    estado,
                    error,
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT estado, COUNT(*) AS c FROM migration_items GROUP BY estado"
            ).fetchall()
        result = {STATUS_PENDING: 0, STATUS_IN_PROGRESS: 0, STATUS_SUCCESS: 0, STATUS_ERROR: 0}
        for row in rows:
            result[row["estado"]] = row["c"]
        result["total"] = sum(result.values())
        return result

    def error_items(self) -> list[MigrationItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM migration_items WHERE estado = ? ORDER BY titulo",
                (STATUS_ERROR,),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> MigrationItem:
        return MigrationItem(
            id_viejo=row["id_viejo"],
            titulo=row["titulo"],
            url_vieja=row["url_vieja"] or "",
            carpeta_origen=row["carpeta_origen"] or "",
            id_nuevo=row["id_nuevo"] or "",
            url_nueva=row["url_nueva"] or "",
            estado=row["estado"],
            error=row["error"] or "",
            updated_at=row["updated_at"] or "",
        )
