from arcgis.gis import GIS

from migracion_esri.drivers.base import MigrationResult
from migracion_esri.drivers.clone_items import CloneItemsDriver
from migracion_esri.drivers.feature_service import FeatureServiceDriver
from migracion_esri.drivers.registry import (
    DRIVER_CLONE_ITEMS,
    DRIVER_FEATURE_SERVICE,
    DRIVER_SKIP,
    FEATURE_SERVICE_TYPE,
    get_driver_name,
)
from migracion_esri.drivers.skip import SkipDriver

__all__ = ["ItemMigrator", "MigrationResult"]


class ItemMigrator:
    def __init__(self, gis_origen: GIS, gis_destino: GIS, logger, folder_map: dict | None = None):
        self.gis_origen = gis_origen
        self.gis_destino = gis_destino
        self.logger = logger
        self.folder_map = folder_map
        self._feature_service = FeatureServiceDriver(gis_origen, gis_destino, logger, folder_map)
        self._clone_items = CloneItemsDriver(gis_origen, gis_destino, logger, folder_map)
        self._skip = SkipDriver()

    def migrate_item(
        self,
        id_viejo: str,
        titulo: str,
        carpeta_origen: str,
        item_type: str = FEATURE_SERVICE_TYPE,
        dest_folder_override: str | None = None,
    ) -> MigrationResult:
        driver_name = get_driver_name(item_type)
        self.logger.info("[%s] Type=%s Driver=%s", titulo, item_type, driver_name)

        if driver_name == DRIVER_SKIP:
            self._skip.migrate(
                id_viejo,
                titulo,
                carpeta_origen,
                item_type,
                dest_folder_override,
            )

        if driver_name == DRIVER_FEATURE_SERVICE:
            return self._feature_service.migrate(
                id_viejo, titulo, carpeta_origen, dest_folder_override
            )

        if driver_name == DRIVER_CLONE_ITEMS:
            return self._clone_items.migrate(
                id_viejo, titulo, carpeta_origen, dest_folder_override
            )

        return self._clone_items.migrate(
            id_viejo, titulo, carpeta_origen, dest_folder_override
        )
