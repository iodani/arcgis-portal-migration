#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import DATA_INPUT, INVENTARIO_CARPETAS, load_config
from migracion_esri.logging_setup import setup_logging
from migracion_esri.workflow_ui import WorkflowSummary, print_failure_summary, print_summary

OUTPUT_COLUMNS = ["Titulo", "ID_Viejo", "URL_Vieja", "Carpeta_Origen"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preparar inventario de migracion desde auditoria"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobrescribir data/input/inventario_migracion.csv si ya existe",
    )
    args = parser.parse_args()

    load_config()
    logger = setup_logging("prepare")
    logger.info("=== INICIO prepare ===")

    try:
        if not INVENTARIO_CARPETAS.exists():
            raise FileNotFoundError(
                f"No existe {INVENTARIO_CARPETAS}. Ejecute primero: python scripts/audit.py"
            )

        if DATA_INPUT.exists() and not args.force:
            raise FileExistsError(
                f"Ya existe {DATA_INPUT}. Edite el archivo, use --force, o borrelo antes de regenerar."
            )

        df = pd.read_csv(INVENTARIO_CARPETAS)
        missing = set(OUTPUT_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(
                f"Columnas faltantes en inventario auditado: {', '.join(sorted(missing))}"
            )

        out = df[OUTPUT_COLUMNS].copy()
        out.to_csv(DATA_INPUT, index=False, encoding="utf-8")

        summary = WorkflowSummary(
            script="prepare",
            lines=[
                f" Filas copiadas: {len(out)}",
                f" Origen:  {INVENTARIO_CARPETAS}",
                f" Destino: {DATA_INPUT}",
                " Edite el CSV y elimine filas que NO desee migrar",
            ],
            next_command="python scripts/migrate.py",
            next_hint="Tras curar el inventario, ejecutar migracion masiva",
        )
        print_summary(summary, logger)
        return 0

    except Exception as exc:
        print_failure_summary("prepare", str(exc), logger)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
