"""Genera un token de ArcGIS para una cuenta del portal DESTINO.

Usado por scripts/generate_db_update.py para refrescar `access_token` /
`token_expires_at` en app.arcgis_upload: el token que esa tabla tiene
guardado hoy fue emitido contra el portal ORIGEN y no sirve para operar
sobre el Feature Service ya migrado a DESTINO.

No usa el objeto GIS de la libreria arcgis (que no expone bien el parametro
`expiration`); llama directamente al endpoint REST `generateToken`.
"""

import time

import requests

DEFAULT_EXPIRATION_MINUTES = 60


class TokenGenerationError(RuntimeError):
    pass


def generate_destino_token(
    portal_url: str,
    username: str,
    password: str,
    expiration_minutes: int = DEFAULT_EXPIRATION_MINUTES,
) -> tuple[str, int]:
    """Pide un token via POST {portal_url}/sharing/rest/generateToken.

    Devuelve (token, expires_at) donde expires_at es un epoch Unix en
    SEGUNDOS (int), formato numerico que espera
    app.arcgis_upload.token_expires_at (ej: 1827843908).
    """
    url = portal_url.rstrip("/") + "/sharing/rest/generateToken"
    try:
        response = requests.post(
            url,
            data={
                "username": username,
                "password": password,
                "client": "referer",
                "referer": portal_url,
                "expiration": expiration_minutes,
                "f": "json",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise TokenGenerationError(f"Fallo de red generando token en {portal_url}: {exc}") from exc
    except ValueError as exc:
        raise TokenGenerationError(f"Respuesta invalida (no JSON) de {url}: {exc}") from exc

    if "token" not in data:
        raise TokenGenerationError(
            f"No se pudo generar el token en {portal_url} para user={username}: "
            f"{data.get('error', data)}"
        )

    token = data["token"]
    expires_ms = data.get("expires")
    if expires_ms:
        expires_at = int(expires_ms / 1000)  # ArcGIS devuelve epoch en milisegundos
    else:
        expires_at = int(time.time()) + expiration_minutes * 60
    return token, expires_at
