# ArcGIS Portal Migration Toolkit

Python tool to **migrate and clone ArcGIS Feature Services** from a source portal (ArcGIS Online or Enterprise) to a destination portal, with full audit trail, checkpoint/resume, and CSV mapping for external database updates.

**Python 3.11** | **arcgis 2.4.x** | Feature Service migration | Batch workflow

Detailed workflow documentation: [docs/WORKFLOW.md](docs/WORKFLOW.md)  
Why IDs/URLs change after migration: [docs/URL_PRESERVATION.md](docs/URL_PRESERVATION.md)  
`app.arcgis_upload` correlation + destino token: [docs/DB_CORRELATION.md](docs/DB_CORRELATION.md)  
**Step-by-step execution guide (install → cleanup → migrate → DB update)**: [docs/GUIA_EJECUCION.md](docs/GUIA_EJECUCION.md)

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

## Workflow — quick start

```bash
python scripts/validate.py   # check .env + connections (no writes)
python scripts/audit.py      # inventory source portal -> inventario_con_carpetas.csv
python scripts/prepare.py    # build inventario_migracion.csv (edit it, or use --db-dsn to filter automatically)
python scripts/migrate.py    # batch migration (resumable, --retry-errors)
python scripts/report.py     # summary + errores_migracion.csv
```

That covers the core cutover (source → destination). Two optional helpers correlate the result with `app.arcgis_upload` and produce a reviewable `.sql` (never auto-executed):

```bash
python scripts/validate_db_correlation.py --db-dsn
python scripts/generate_db_update.py --db-dsn
```

**For the full, detailed instructions** (every flag, what to check at each step, Camino A/B for DB access, cleanup helpers), see:

- [docs/GUIA_EJECUCION.md](docs/GUIA_EJECUCION.md) — step-by-step execution runbook (Spanish)
- [docs/WORKFLOW.md](docs/WORKFLOW.md) — technical reference: phases, drivers, file formats, diagrams (English)
- [docs/DB_CORRELATION.md](docs/DB_CORRELATION.md) — `app.arcgis_upload` correlation + token generation details
- [docs/URL_PRESERVATION.md](docs/URL_PRESERVATION.md) — why IDs/URLs always change on a real migration

---

## Quick reference

| Action | Command |
|--------|---------|
| Validate connections | `python scripts/validate.py` |
| Audit | `python scripts/audit.py` |
| Prepare inventory | `python scripts/prepare.py` |
| Prepare inventory filtered by DB | `python scripts/prepare.py --db-dsn` |
| Migration | `python scripts/migrate.py` |
| Resume | `python scripts/migrate.py` |
| Retry errors | `python scripts/migrate.py --retry-errors` |
| Report | `python scripts/report.py` |
| Validate DB correlation | `python scripts/validate_db_correlation.py --db-dsn` |
| Generate DB update SQL | `python scripts/generate_db_update.py --db-dsn` |
| Cleanup destination test items | `python scripts/cleanup_destino.py --folder <carpeta>` |
| Cleanup local generated files | `python scripts/cleanup_local.py --yes` |

---

## Project structure

```
migracion_esri/
├── docs/              # GUIA_EJECUCION.md, WORKFLOW.md, URL_PRESERVATION.md, DB_CORRELATION.md
├── scripts/           # validate, audit, prepare, migrate, report, validate_db_correlation,
│                      # generate_db_update, cleanup_destino, cleanup_local
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
| `data/output/validacion_correlacion.csv` | DB correlation key check (optional) |
| `data/output/update_arcgis_upload.sql` | `app.arcgis_upload` UPDATE statements for manual review (optional) |
| `state/migration_state.db` | State for resume |
| `logs/<script>_*.log` | Detailed log with error context |
