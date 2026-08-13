import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

DATA_DIR = PROJECT_ROOT / "data"
DATA_INPUT = DATA_DIR / "input" / "inventario_migracion.csv"
INVENTARIO_PILOT = DATA_DIR / "input" / "inventario_pilot.csv"
DATA_OUTPUT = DATA_DIR / "output"
INVENTARIO_CARPETAS = DATA_OUTPUT / "inventario_con_carpetas.csv"
MAPEO_MIGRACION = DATA_OUTPUT / "mapeo_migracion.csv"
ERRORES_MIGRACION = DATA_OUTPUT / "errores_migracion.csv"
PILOT_MATRIX = DATA_OUTPUT / "pilot_matrix.csv"

STATE_DIR = PROJECT_ROOT / "state"
STATE_DB = STATE_DIR / "migration_state.db"
PILOT_STATE_DB = STATE_DIR / "pilot_state.db"
PILOT_MAPEO = DATA_OUTPUT / "mapeo_pilot.csv"
DEFAULT_PILOT_FOLDER = "MIGRACION_PILOTO_TIPOS"

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
