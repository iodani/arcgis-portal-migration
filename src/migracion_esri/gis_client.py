from dataclasses import dataclass

from arcgis.gis import GIS

from migracion_esri.config import get_env, validate_env_vars
from migracion_esri.logging_setup import log_error_context


@dataclass
class PortalConnection:
    name: str
    url: str
    username: str


def connect_portal(name: str, url_key: str, user_key: str, pass_key: str, logger) -> PortalConnection:
    url = get_env(url_key)
    user = get_env(user_key)
    password = get_env(pass_key)
    logger.info("Conectando portal=%s url=%s user=%s", name, url, user)
    try:
        gis = GIS(url, user, password)
        username = gis.users.me.username
        logger.info("Portal %s conectado: user=%s url=%s", name, username, gis.url)
        return PortalConnection(name=name, url=gis.url, username=username)
    except Exception as exc:
        log_error_context(
            logger,
            "validate",
            "Fallo de conexión",
            portal=name,
            exc=exc,
        )
        raise


def validate_connections(logger) -> tuple[GIS, GIS, PortalConnection, PortalConnection]:
    validate_env_vars()
    logger.info("Variables .env verificadas (%d claves)", 6)

    gis_origen = GIS(get_env("ORIGEN_URL"), get_env("ORIGEN_USER"), get_env("ORIGEN_PASS"))
    origen = PortalConnection("origen", gis_origen.url, gis_origen.users.me.username)
    logger.info("Portal origen conectado: user=%s url=%s", origen.username, origen.url)

    gis_destino = GIS(get_env("DESTINO_URL"), get_env("DESTINO_USER"), get_env("DESTINO_PASS"))
    destino = PortalConnection("destino", gis_destino.url, gis_destino.users.me.username)
    logger.info("Portal destino conectado: user=%s url=%s", destino.username, destino.url)

    return gis_origen, gis_destino, origen, destino
