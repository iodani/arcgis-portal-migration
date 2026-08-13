from migracion_esri.drivers.base import SkipMigration
from migracion_esri.drivers.registry import SKIP_TYPES


class SkipDriver:
    def migrate(
        self,
        id_viejo: str,
        titulo: str,
        carpeta_origen: str,
        item_type: str,
        dest_folder_override: str | None = None,
    ) -> None:
        reason = f"Tipo no soportado para migración: {item_type}"
        if item_type in SKIP_TYPES:
            reason = f"Tipo excluido por diseño: {item_type}"
        raise SkipMigration(reason)
