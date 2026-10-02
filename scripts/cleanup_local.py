#!/usr/bin/env python3
"""Limpia archivos locales generados (logs/, data/output/*, state/*.db, temp/*)
para arrancar un run de prueba desde cero.

No toca ArcGIS Online ni ninguna base de datos: solo borra archivos locales
de este repo. Para limpiar items creados en el portal destino, use
scripts/cleanup_destino.py.
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from migracion_esri.config import DATA_OUTPUT, LOGS_DIR, STATE_DIR, TEMP_DIR, load_config  # noqa: E402
from migracion_esri.workflow_ui import WorkflowSummary, print_summary  # noqa: E402

KEEP_FILES = {".gitkeep"}
TARGET_DIRS = (LOGS_DIR, DATA_OUTPUT, STATE_DIR, TEMP_DIR)


def _collect_and_clear(path: Path, dry_run: bool) -> tuple[list[Path], list[tuple[Path, str]]]:
    removed: list[Path] = []
    locked: list[tuple[Path, str]] = []
    if not path.exists():
        return removed, locked
    for child in sorted(path.iterdir()):
        if child.name in KEEP_FILES:
            continue
        if dry_run:
            removed.append(child)
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed.append(child)
        except OSError as exc:
            locked.append((child, str(exc)))
    return removed, locked


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Limpia logs/, data/output/*, state/*.db y temp/* (archivos locales generados)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo listar, sin borrar")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirmar el borrado (requerido si no se usa --dry-run)",
    )
    args = parser.parse_args()

    load_config()

    if not args.dry_run and not args.yes:
        print(
            "Esto borrara el contenido de:\n"
            f"  - {LOGS_DIR}\n"
            f"  - {DATA_OUTPUT}\n"
            f"  - {STATE_DIR}\n"
            f"  - {TEMP_DIR}\n"
            "Use --yes para confirmar o --dry-run para solo revisar que se borraria."
        )
        return 1

    removed: list[Path] = []
    locked: list[tuple[Path, str]] = []
    for target_dir in TARGET_DIRS:
        got, skipped = _collect_and_clear(target_dir, args.dry_run)
        removed.extend(got)
        locked.extend(skipped)

    verb = "Se borrarian" if args.dry_run else "Borrados"
    lines = [f" {verb}: {len(removed)} archivos/carpetas"]
    lines.extend(f"   - {p}" for p in removed[:50])
    if len(removed) > 50:
        lines.append(f"   ... y {len(removed) - 50} mas")
    if locked:
        lines.append(f" No se pudieron borrar (en uso): {len(locked)}")
        lines.extend(f"   - {p}" for p, _ in locked)

    summary = WorkflowSummary(
        script="cleanup_local",
        lines=lines or [" Nada que borrar; ya esta limpio."],
        next_command="python scripts/validate.py",
        next_hint="Arrancar un run de prueba desde cero",
    )
    print_summary(summary)
    return 1 if locked else 0


if __name__ == "__main__":
    raise SystemExit(main())
