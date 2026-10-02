import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

DATA_DIR = PROJECT_ROOT / "data"
DATA_INPUT = DATA_DIR / "input" / "inventario_migracion.csv"
DATA_OUTPUT = DATA_DIR / "output"
INVENTARIO_CARPETAS = DATA_OUTPUT / "inventario_con_carpetas.csv"
MAPEO_MIGRACION = DATA_OUTPUT / "mapeo_migracion.csv"
ERRORES_MIGRACION = DATA_OUTPUT / "errores_migracion.csv"
VALIDACION_CORRELACION = DATA_OUTPUT / "validacion_correlacion.csv"
UPDATE_ARCGIS_UPLOAD_SQL = DATA_OUTPUT / "update_arcgis_upload.sql"
SIN_MATCH_ARCGIS_UPLOAD = DATA_OUTPUT / "sin_match_arcgis_upload.csv"
SIN_MATCH_INVENTARIO_DB = DATA_OUTPUT / "sin_match_inventario_db.csv"

STATE_DIR = PROJECT_ROOT / "state"
STATE_DB = STATE_DIR / "migration_state.db"
# Usados por migrate.py --pilot-folder (corrida de prueba en carpeta aislada
# de destino, con estado/mapeo separados del flujo principal).
PILOT_STATE_DB = STATE_DIR / "pilot_state.db"
PILOT_MAPEO = DATA_OUTPUT / "mapeo_pilot.csv"

LOGS_DIR = PROJECT_ROOT / "logs"
TEMP_DIR = PROJECT_ROOT / "temp"
LEGACY_DIR = PROJECT_ROOT / "legacy"

ENV_KEYS = (
    "ORIGEN_URL",
    "ORIGEN_USER",
    "ORIGEN_PASS",
    "DESTINO_URL",
    "DESTINO_USER",
    "DESTINO_PASS",
)

# Variable opcional para correlacionar con la BD de la plataforma (app.arcgis_upload).
# No forma parte de ENV_KEYS: el flujo principal de migracion no la requiere.
PG_DSN_ENV_KEY = "PGDSN"
PG_DEFAULT_SCHEMA = "app"

# Expiracion (minutos) del token nuevo que generate_db_update.py pide para el
# portal DESTINO al armar el UPDATE de access_token. Configurable en .env.
TOKEN_EXPIRATION_ENV_KEY = "TOKEN_EXPIRATION_MINUTES"
DEFAULT_TOKEN_EXPIRATION_MINUTES = 60


def get_token_expiration_minutes() -> int:
    load_config()
    raw = os.getenv(TOKEN_EXPIRATION_ENV_KEY, "").strip()
    if not raw:
        return DEFAULT_TOKEN_EXPIRATION_MINUTES
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(
            f"{TOKEN_EXPIRATION_ENV_KEY} debe ser un entero (minutos), valor actual: {raw!r}"
        )
    if value <= 0:
        raise ValueError(f"{TOKEN_EXPIRATION_ENV_KEY} debe ser mayor a 0, valor actual: {value}")
    return value


def ensure_dirs() -> None:
    for path in (DATA_OUTPUT, STATE_DIR, LOGS_DIR, TEMP_DIR, DATA_DIR / "input"):
        path.mkdir(parents=True, exist_ok=True)


def load_config() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    ensure_dirs()


def get_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise ValueError(f"Variable de entorno requerida no configurada: {key}")
    return value


def validate_env_vars() -> dict[str, str]:
    load_config()
    return {key: get_env(key) for key in ENV_KEYS}


def get_pg_dsn() -> tuple[str, str]:
    """Lee el DSN de Postgres (solo lectura) desde una unica variable de entorno.

    PGDSN acepta cualquier formato que entienda psycopg2.connect(), por ejemplo:
      - URI:     postgresql://user:password@host:5432/dbname
      - keyword: host=fdsu_postgres port=5432 dbname=fdsu user=... password=...

    Devuelve (dsn, schema). No requerido por el flujo principal de migracion;
    solo lo usan validate_db_correlation.py y generate_db_update.py cuando se
    invocan con --db-dsn.
    """
    load_config()
    dsn = os.getenv(PG_DSN_ENV_KEY, "").strip()
    if not dsn:
        raise ValueError(
            f"Variable de entorno requerida no configurada: {PG_DSN_ENV_KEY} "
            "(ej: postgresql://user:password@host:5432/dbname)"
        )
    schema = os.getenv("PGSCHEMA", PG_DEFAULT_SCHEMA).strip() or PG_DEFAULT_SCHEMA
    return dsn, schema
