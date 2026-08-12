# Migración ArcGIS Online → Portal Destino

Workflow profesional para clonar Feature Services entre portales ArcGIS, con trazabilidad completa (logs + CSV de mapeo), checkpoint/resume y reporte de errores.

**Python 3.11** | **arcgis 2.4.x**

Documentación detallada del workflow: [docs/WORKFLOW.md](docs/WORKFLOW.md)

---

## Requisitos

- Python 3.11 (`py -3.11 --version`)
- Cuenta **origen** con permiso Export Data sobre las capas
- Cuenta **destino** con permiso Publish y crear carpetas
- Acceso de red a ambos portales

Este proyecto **no actualiza bases de datos**. El entregable para BD externa es `data/output/mapeo_migracion.csv`.

---

## Instalación (primera vez)

Ejecutar desde la raíz del proyecto (`migracion_esri/`).

### Git Bash

```bash
cd /c/ruta/a/migracion_esri
py -3.11 -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env con credenciales
```

### PowerShell

```powershell
cd C:\ruta\a\migracion_esri
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Editar .env con credenciales
```

### CMD

```cmd
cd C:\ruta\a\migracion_esri
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
```

### Sesiones posteriores — activar entorno

| Shell | Comando |
|-------|---------|
| Git Bash | `source .venv/Scripts/activate` |
| PowerShell | `.\.venv\Scripts\Activate.ps1` |
| CMD | `.venv\Scripts\activate.bat` |

---

## Configuración (`.env`)

```env
ORIGEN_URL=https://your-org.maps.arcgis.com/
ORIGEN_USER=...
ORIGEN_PASS=...
DESTINO_URL=https://www.arcgis.com
DESTINO_USER=...
DESTINO_PASS=...
```

Checklist antes de ejecutar:

- [ ] `.env` configurado
- [ ] venv activo (`(.venv)` en el prompt)
- [ ] `python --version` → 3.11.x

---

## Workflow — paso a paso

### Paso 1 — Validar conexiones (no migra nada)

```bash
python scripts/validate.py
```

Comprueba variables `.env` y login en origen y destino. **No exporta, sube ni publica capas.**

Al finalizar muestra resumen + `NEXT -> python scripts/audit.py`

### Paso 2 — Auditoría

```bash
python scripts/audit.py
```

Genera `data/output/inventario_con_carpetas.csv` con todos los Feature Services del origen.

### Paso 3 — Preparar inventario de migración

```bash
python scripts/prepare.py
```

Copia automáticamente `data/output/inventario_con_carpetas.csv` → `data/input/inventario_migracion.csv`.

Luego **edite el CSV y elimine filas** de capas que no desee migrar.

Para regenerar desde cero: `python scripts/prepare.py --force`

Documentación detallada: [docs/WORKFLOW.md](docs/WORKFLOW.md)

### Paso 4 — Migración masiva

```bash
python scripts/migrate.py
```

- Progreso en consola y `logs/migrate_*.log`
- Estado persistente en `state/migration_state.db`
- Mapeo por item en `data/output/mapeo_migracion.csv`

### Paso 5 — Reanudar si se interrumpe

```bash
python scripts/migrate.py
```

- `success` → se salta
- `in_progress` / `pending` → se procesa
- `error` → se salta (usar `--retry-errors` para reintentar)

```bash
python scripts/migrate.py --retry-errors
```

### Paso 6 — Reporte

```bash
python scripts/report.py
```

Resumen total/éxito/error/pendiente. Exporta `data/output/errores_migracion.csv`.

### Paso 7 — BD externa

Usar `data/output/mapeo_migracion.csv` en otro entorno para actualizar IDs y URLs. Ver [docs/WORKFLOW.md](docs/WORKFLOW.md) para formato y pseudocódigo.

---

## Referencia rápida

| Acción | Comando |
|--------|---------|
| Validar conexiones | `python scripts/validate.py` |
| Auditoría | `python scripts/audit.py` |
| Preparar inventario | `python scripts/prepare.py` |
| Migración | `python scripts/migrate.py` |
| Reanudar | `python scripts/migrate.py` |
| Reintentar errores | `python scripts/migrate.py --retry-errors` |
| Reporte | `python scripts/report.py` |

---

## Estructura del proyecto

```
migracion_esri/
├── docs/              # WORKFLOW.md
├── scripts/           # validate, audit, prepare, migrate, report
├── src/migracion_esri/
├── data/
│   ├── input/         # inventario_migracion.csv (local, gitignored)
│   └── output/        # generados en ejecucion (gitignored)
├── state/             # migration_state.db (gitignored)
├── logs/
└── temp/
```

---

## Archivos de salida

| Archivo | Propósito |
|---------|-----------|
| `data/output/inventario_con_carpetas.csv` | Inventario completo origen |
| `data/input/inventario_migracion.csv` | Lista curada a migrar |
| `data/output/mapeo_migracion.csv` | Mapeo ID/URL viejo → nuevo |
| `data/output/errores_migracion.csv` | Items no clonables |
| `state/migration_state.db` | Estado para resume |
| `logs/<script>_*.log` | Log detallado con contexto de errores |
