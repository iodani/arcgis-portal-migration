from arcgis.gis import GIS

from migracion_esri.drivers.base import MigrationResult
from migracion_esri.folders import ensure_folder
from migracion_esri.logging_setup import log_error_context


class CloneItemsDriver:
    def __init__(self, gis_origen: GIS, gis_destino: GIS, logger, folder_map: dict | None = None):
        self.gis_origen = gis_origen
        self.gis_destino = gis_destino
        self.logger = logger
        self.folder_map = folder_map

    def migrate(
        self,
        id_viejo: str,
        titulo: str,
        carpeta_origen: str,
        dest_folder_override: str | None = None,
    ) -> MigrationResult:
        self.logger.info("[%s] Obteniendo item origen (clone_items)", titulo)
        item = self.gis_origen.content.get(id_viejo)
        if not item:
            raise ValueError(f"Item no encontrado en origen: {id_viejo}")

        if dest_folder_override:
            folder_name = dest_folder_override
        elif carpeta_origen and carpeta_origen != "RAIZ":
            folder_name = carpeta_origen
        else:
            folder_name = None

        if folder_name:
            ensure_folder(self.gis_destino, folder_name)

        self.logger.info(
            "[%s] Clonando a destino (carpeta=%s)",
            titulo,
            folder_name or "RAIZ",
        )
        try:
            cloned = self.gis_destino.content.clone_items(
                items=[item],
                folder=folder_name,
                copy_data=True,
                search_existing_items=True,
            )
        except Exception as exc:
            log_error_context(
                self.logger,
                "migrate",
                "Fallo en clone_items",
                portal="destino",
                fase="clone",
                id_viejo=id_viejo,
                titulo=titulo,
                exc=exc,
            )
            raise

        if not cloned:
            raise RuntimeError("clone_items no devolvió items clonados")

        nuevo = cloned[0]
        url = ""
        try:
            url = nuevo.url or ""
        except Exception:
            try:
                url = nuevo.get("url", "") if hasattr(nuevo, "get") else ""
            except Exception:
                url = ""

        return MigrationResult(id_nuevo=nuevo.id, url_nueva=url)
