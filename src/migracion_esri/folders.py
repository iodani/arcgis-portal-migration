from arcgis.gis import GIS


def build_folder_map(gis: GIS) -> dict[str | None, str]:
    folder_map: dict[str | None, str] = {}
    for folder in gis.users.me.folders:
        props = folder.properties or {}
        folder_id = props.get("id")
        if folder_id:
            folder_map[folder_id] = folder.name
    folder_map[None] = "RAIZ"
    folder_map[""] = "RAIZ"
    return folder_map


def resolve_folder_name(gis: GIS, owner_folder_id: str | None, folder_map: dict | None = None) -> str:
    if folder_map is None:
        folder_map = build_folder_map(gis)
    return folder_map.get(owner_folder_id, "RAIZ")


def ensure_folder(gis: GIS, folder_name: str) -> str:
    if not folder_name or folder_name == "RAIZ":
        return folder_name
    folder_obj = gis.content.folders.get(folder=folder_name)
    if folder_obj is None:
        gis.content.folders.create(folder_name)
    return folder_name
