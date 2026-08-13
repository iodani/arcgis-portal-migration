#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import INVENTARIO_CARPETAS, INVENTARIO_PILOT, PILOT_MATRIX, load_config
from migracion_esri.logging_setup import setup_logging
from migracion_esri.workflow_ui import WorkflowSummary, print_failure_summary, print_summary

PILOT_COLUMNS = [
    "Titulo",
    "ID_Viejo",
    "URL_Vieja",
    "Carpeta_Origen",
    "Type",
    "Fase",
    "Driver",
]


def select_one_per_type(df: pd.DataFrame) -> pd.DataFrame:
    if "Tamaño_MB" in df.columns:
        sorted_df = df.sort_values(["Type", "Tamaño_MB"], ascending=[True, True])
    else:
        sorted_df = df.sort_values(["Type", "Titulo"])
    return sorted_df.groupby("Type", as_index=False).first()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generar inventario piloto: 1 item por Type ArcGIS"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobrescribir inventario_pilot.csv si ya existe",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generar pilot_matrix.csv cruzando mapeo con inventario piloto",
    )
    args = parser.parse_args()

    load_config()
    logger = setup_logging("prepare_pilot")
    logger.info("=== INICIO prepare_pilot ===")

    try:
        if args.report:
            return _write_pilot_matrix(logger)

        if not INVENTARIO_CARPETAS.exists():
            raise FileNotFoundError(
                f"No existe {INVENTARIO_CARPETAS}. Ejecute primero: python scripts/audit.py"
            )

        if INVENTARIO_PILOT.exists() and not args.force:
            raise FileExistsError(
                f"Ya existe {INVENTARIO_PILOT}. Use --force para regenerar."
            )

        df = pd.read_csv(INVENTARIO_CARPETAS)
        if "Type" not in df.columns:
            raise ValueError("Inventario sin columna Type. Ejecute audit.py actualizado.")

        pilot = select_one_per_type(df)
        missing_cols = set(PILOT_COLUMNS) - set(pilot.columns)
        if missing_cols:
            raise ValueError(f"Columnas faltantes: {', '.join(sorted(missing_cols))}")

        pilot = pilot[PILOT_COLUMNS]
        pilot.to_csv(INVENTARIO_PILOT, index=False, encoding="utf-8")

        types_total = df["Type"].nunique()
        if len(pilot) != types_total:
            logger.warning(
                "Filas piloto (%d) != types distintos (%d)", len(pilot), types_total
            )

        for _, row in pilot.iterrows():
            logger.info("Type=%s | %s | id=%s", row["Type"], row["Titulo"], row["ID_Viejo"])

        summary = WorkflowSummary(
            script="prepare_pilot",
            lines=[
                f" Types en origen: {types_total}",
                f" Filas piloto (1 por Type): {len(pilot)}",
                f" Archivo: {INVENTARIO_PILOT}",
            ],
            next_command=(
                "python scripts/migrate.py --inventory data/input/inventario_pilot.csv "
                "--pilot-folder MIGRACION_PILOTO_TIPOS"
            ),
            next_hint="Migrar piloto en carpeta aislada del destino",
        )
        print_summary(summary, logger)
        return 0

    except Exception as exc:
        print_failure_summary("prepare_pilot", str(exc), logger)
        return 1


def _write_pilot_matrix(logger) -> int:
    from migracion_esri.config import MAPEO_MIGRACION, PILOT_MAPEO

    mapeo_path = PILOT_MAPEO if PILOT_MAPEO.exists() else MAPEO_MIGRACION
    if not INVENTARIO_PILOT.exists():
        raise FileNotFoundError(f"No existe {INVENTARIO_PILOT}")
    if not mapeo_path.exists():
        raise FileNotFoundError(f"No existe {mapeo_path}")

    pilot = pd.read_csv(INVENTARIO_PILOT)
    mapeo = pd.read_csv(mapeo_path)
    latest = mapeo.sort_values("Fecha").groupby("ID_Viejo", as_index=False).last()
    matrix = pilot.merge(
        latest[["ID_Viejo", "Estado", "Error", "ID_Nuevo", "URL_Nueva"]],
        on="ID_Viejo",
        how="left",
    )
    matrix = matrix[["Type", "Driver", "Titulo", "ID_Viejo", "Estado", "Error", "ID_Nuevo", "URL_Nueva"]]
    matrix.to_csv(PILOT_MATRIX, index=False, encoding="utf-8")

    summary = WorkflowSummary(
        script="prepare_pilot",
        lines=[
            f" Matriz piloto: {PILOT_MATRIX}",
            f" Filas: {len(matrix)}",
        ],
        next_command="python scripts/cleanup_pilot.py",
        next_hint="Eliminar items de prueba en destino tras revisar matriz",
    )
    print_summary(summary, logger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
