# ArcGIS Portal Migration Toolkit

Python tool to **migrate and clone ArcGIS Feature Services** from a source portal (ArcGIS Online or Enterprise) to a destination portal, with full audit trail, checkpoint/resume, and CSV mapping for external database updates.

**Python 3.11** | **arcgis 2.4.x** | Feature Service migration | Batch workflow

Detailed workflow documentation: [docs/WORKFLOW.md](docs/WORKFLOW.md)

---

## Requirements

- Python 3.11 (`py -3.11 --version`)
- **Source** account with Export Data permission on layers
- **Destination** account with Publish permission and ability to create folders
- Network access to both portals

This project **does not update databases**. The deliverable for external DB use is `data/output/mapeo_migracion.csv`.

---

## Installation (first time)

Run from the project root (`migracion_esri/`).

### Git Bash

```bash
cd /c/path/to/migracion_esri
py -3.11 -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with credentials
```

### PowerShell

```powershell
cd C:\path\to\migracion_esri
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with credentials
```

### CMD

```cmd
cd C:\path\to\migracion_esri
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
```

### Subsequent sessions — activate environment

| Shell | Command |
|-------|---------|
| Git Bash | `source .venv/Scripts/activate` |
| PowerShell | `.\.venv\Scripts\Activate.ps1` |
| CMD | `.venv\Scripts\activate.bat` |

---

## Configuration (`.env`)

```env
ORIGEN_URL=https://your-org.maps.arcgis.com/
ORIGEN_USER=...
ORIGEN_PASS=...
DESTINO_URL=https://www.arcgis.com
DESTINO_USER=...
DESTINO_PASS=...
```

Checklist before running:

- [ ] `.env` configured
- [ ] venv active (`(.venv)` in prompt)
- [ ] `python --version` → 3.11.x

---

## Workflow — step by step

### Step 1 — Validate connections (does not migrate)

```bash
python scripts/validate.py
```

Checks `.env` variables and login to source and destination. **Does not export, upload, or publish layers.**

On completion shows summary + `NEXT -> python scripts/audit.py`

### Step 2 — Audit

```bash
python scripts/audit.py
```

Generates `data/output/inventario_con_carpetas.csv` with all Feature Services from the source portal.

### Step 3 — Prepare migration inventory

```bash
python scripts/prepare.py
```

Automatically copies `data/output/inventario_con_carpetas.csv` → `data/input/inventario_migracion.csv`.

Then **edit the CSV and remove rows** for layers you do not want to migrate.

To regenerate from scratch: `python scripts/prepare.py --force`

Detailed documentation: [docs/WORKFLOW.md](docs/WORKFLOW.md)

### Step 4 — Batch migration

```bash
python scripts/migrate.py
```

- Progress in console and `logs/migrate_*.log`
- Persistent state in `state/migration_state.db`
- Per-item mapping in `data/output/mapeo_migracion.csv`

### Step 5 — Resume if interrupted

```bash
python scripts/migrate.py
```

- `success` → skipped
- `in_progress` / `pending` → processed
- `error` → skipped (use `--retry-errors` to retry)

```bash
python scripts/migrate.py --retry-errors
```

### Step 6 — Report

```bash
python scripts/report.py
```

Summary of total/success/error/pending. Exports `data/output/errores_migracion.csv`.

### Step 7 — External database

Use `data/output/mapeo_migracion.csv` in another environment to update IDs and URLs. See [docs/WORKFLOW.md](docs/WORKFLOW.md) for format and pseudocode.

---

## Quick reference

| Action | Command |
|--------|---------|
| Validate connections | `python scripts/validate.py` |
| Audit | `python scripts/audit.py` |
| Prepare inventory | `python scripts/prepare.py` |
| Migration | `python scripts/migrate.py` |
| Resume | `python scripts/migrate.py` |
| Retry errors | `python scripts/migrate.py --retry-errors` |
| Report | `python scripts/report.py` |

---

## Project structure

```
migracion_esri/
├── docs/              # WORKFLOW.md
├── scripts/           # validate, audit, prepare, migrate, report
├── src/migracion_esri/
├── data/
│   ├── input/         # inventario_migracion.csv (local, gitignored)
│   └── output/        # generated at runtime (gitignored)
├── state/             # migration_state.db (gitignored)
├── logs/
└── temp/
```

---

## Output files

| File | Purpose |
|------|---------|
| `data/output/inventario_con_carpetas.csv` | Full source inventory |
| `data/input/inventario_migracion.csv` | Curated list to migrate |
| `data/output/mapeo_migracion.csv` | Old → new ID/URL mapping |
| `data/output/errores_migracion.csv` | Items that could not be cloned |
| `state/migration_state.db` | State for resume |
| `logs/<script>_*.log` | Detailed log with error context |
