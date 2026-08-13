import os
import time

from arcgis.gis import GIS

from migracion_esri.config import TEMP_DIR
from migracion_esri.drivers.base import MigrationResult
from migracion_esri.folders import ensure_folder, resolve_folder_name
from migracion_esri.logging_setup import log_error_context


class FeatureServiceDriver:
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
        temp_export_item = None
        path_zip = None
        nuevo_item_fgdb = None

        try:
            self.logger.info("[%s] Obteniendo item origen", titulo)
            item = self.gis_origen.content.get(id_viejo)
            if not item:
                raise ValueError(f"Item no encontrado en origen: {id_viejo}")

            if dest_folder_override:
                folder_name = dest_folder_override
            else:
                folder_name = carpeta_origen
                if not folder_name or folder_name == "RAIZ":
                    folder_name = resolve_folder_name(
                        self.gis_origen, item.ownerFolder, self.folder_map
                    )

            ensure_folder(self.gis_destino, folder_name)
            dest_folder = None if folder_name in ("", "RAIZ") else folder_name

            self.logger.info("[%s] Habilitando exportación", titulo)
            item.update(item_properties={"capabilities": "Query,Extract"})

            self.logger.info("[%s] Exportando FGDB en origen", titulo)
            export_name = f"tmp_mig_{int(time.time())}"
            try:
                temp_export_item = item.export(export_name, "File Geodatabase")
            except Exception as exc:
                log_error_context(
                    self.logger,
                    "migrate",
                    "Fallo en exportación",
                    portal="origen",
                    fase="export",
                    id_viejo=id_viejo,
                    titulo=titulo,
                    exc=exc,
                )
                raise

            self.logger.info("[%s] Descargando archivo local", titulo)
            try:
                path_zip = temp_export_item.download(save_path=str(TEMP_DIR))
            except Exception as exc:
                log_error_context(
                    self.logger,
                    "migrate",
                    "Fallo en descarga",
                    portal="origen",
                    fase="download",
                    id_viejo=id_viejo,
                    titulo=titulo,
                    exc=exc,
                )
                raise

            self.logger.info("[%s] Subiendo FGDB a destino (carpeta=%s)", titulo, dest_folder or "RAIZ")
            props = {"title": titulo, "type": "File Geodatabase"}
            if item.tags:
                props["tags"] = item.tags
            try:
                nuevo_item_fgdb = self.gis_destino.content.add(
                    item_properties=props,
                    data=path_zip,
                    folder=dest_folder,
                )
            except Exception as exc:
                log_error_context(
                    self.logger,
                    "migrate",
                    "Fallo en subida",
                    portal="destino",
                    fase="upload",
                    id_viejo=id_viejo,
                    titulo=titulo,
                    exc=exc,
                )
                raise

            self.logger.info("[%s] Publicando servicio", titulo)
            try:
                capa_publicada = nuevo_item_fgdb.publish()
            except Exception as exc:
                log_error_context(
                    self.logger,
                    "migrate",
                    "Fallo en publicación",
                    portal="destino",
                    fase="publish",
                    id_viejo=id_viejo,
                    titulo=titulo,
                    exc=exc,
                )
                raise

            self.logger.info("[%s] Eliminando FGDB temporal en destino", titulo)
            try:
                nuevo_item_fgdb.delete()
            except Exception as exc:
                self.logger.warning("[%s] No se pudo borrar FGDB destino: %s", titulo, exc)

            return MigrationResult(id_nuevo=capa_publicada.id, url_nueva=capa_publicada.url or "")

        finally:
            if temp_export_item:
                try:
                    temp_export_item.delete()
                except Exception:
                    pass
            if path_zip and os.path.exists(path_zip):
                try:
                    os.remove(path_zip)
                except Exception:
                    pass
