# Guia de ejecucion: migracion completa + correlacion con `app.arcgis_upload`

Guia operativa paso a paso, de principio a fin, para ejecutar este toolkit
sobre Git Bash (Windows). Cubre todo el flujo: desde instalar dependencias
hasta dejar listo el `.sql` (o, alternativamente, un migration de Yii)
que actualiza `app.arcgis_upload` en el portal destino.

El flujo es **el mismo** sin importar como se acceda a `app.arcgis_upload`.
Solo se bifurca en dos caminos en los pasos 7 y 8 (los que leen la tabla):

- **Camino A — Acceso directo a Postgres** (`--db-dsn`). Es la forma
  completa/integra: el script lee la tabla en vivo. Requiere que esta
  maquina tenga red hacia la base de datos y las credenciales en `.env`.
- **Camino B — Export manual en CSV** (`--arcgis-upload-csv`). Para cuando
  no se quiere o no se puede dar acceso directo a la BD desde esta maquina:
  alguien exporta `app.arcgis_upload` a un CSV y se lo pasa al script.

Elige un camino (o prueba ambos) en los pasos 7 y 8. El resto de los pasos
(1 a 6) es idéntico.

Ningun script de este toolkit ejecuta `INSERT`/`UPDATE`/`DELETE` sobre la
base de datos de la plataforma. El unico artefacto que modifica
`app.arcgis_upload` es el `.sql` (o el migration `.php` con `--format
yii`) generado en el Paso 8, y se aplica manualmente fuera de este
toolkit.

---

## Checklist rapido

- [ ] Paso 0 — Prerrequisitos y dependencias instaladas
- [ ] Paso 0.1 — Limpieza local (dejar todo en cero)
- [ ] Paso 1 — `validate.py` (conexiones OK)
- [ ] Paso 2 — `audit.py` (inventario de origen)
- [ ] Paso 3 — `prepare.py` (manual o `--db-dsn`/`--arcgis-upload-csv`)
- [ ] Paso 4 — Curar el CSV (solo si usaste el modo manual)
- [ ] Paso 5 — `migrate.py` (migracion masiva)
- [ ] Paso 6 — `report.py` (reporte final)
- [ ] Paso 7 — `validate_db_correlation.py` (Camino A o B)
- [ ] Paso 8 — `generate_db_update.py` (Camino A o B; `--format sql` o `--format yii`)
- [ ] Paso 9 — Entregar `.sql` o `.php` al DBA / equipo de datos
- [ ] Paso 10 — Verificacion final

---

## Paso 0 — Prerrequisitos e instalacion de dependencias

Solo la primera vez (o si `requirements.txt` cambio).

```bash
cd /c/path/to/migracion_esri

# Si no existe el entorno virtual, crearlo
py -3.11 -m venv .venv

# Activar el entorno (cada sesion nueva de Git Bash)
source .venv/Scripts/activate

# Instalar/actualizar dependencias (incluye psycopg2-binary para Camino A)
pip install -r requirements.txt

# Si no existe .env, crearlo desde la plantilla
[ -f .env ] || cp .env.example .env
```

Edita `.env` con:

- `ORIGEN_URL` / `ORIGEN_USER` / `ORIGEN_PASS`: cuenta del portal origen.
  **Importante**: debe ser la cuenta propietaria real de los servicios
  (p. ej. la cuenta de sistema `appdev_FDSU`), no un admin generico — si no,
  el audit puede no ver items privados de esa cuenta (ver
  [DB_CORRELATION.md](DB_CORRELATION.md)).
- `DESTINO_URL` / `DESTINO_USER` / `DESTINO_PASS`: cuenta del portal destino.
- Si vas a usar el **Camino A** en los pasos 7/8: `PGDSN` y `PGSCHEMA`
  (ver ejemplos de formato dentro de `.env.example`).

Verificacion: `python -c "import psycopg2; print('ok')"` no debe dar error
(solo necesario para Camino A).

---

## Paso 0.1 — Limpieza local (empezar desde cero)

Recomendado antes de cada corrida de prueba, para no mezclar logs/estado
de corridas anteriores.

```bash
# Ver que se borraria, sin borrar nada
python scripts/cleanup_local.py --dry-run

# Borrar de verdad: logs/, data/output/*, state/*.db, temp/*
python scripts/cleanup_local.py --yes
```

Esto **no** toca ArcGIS Online ni ninguna base de datos — solo archivos
locales de este repo. Si quedan items de pruebas anteriores en el portal
**destino**, usa el Anexo al final de esta guia (`cleanup_destino.py`)
antes de seguir.

---

## Paso 1 — Validar conexiones

```bash
python scripts/validate.py
```

Que revisar: el resumen debe mostrar `Origen: conectado` y
`Destino: conectado` con los usuarios correctos. Si falla aqui, corrige
`.env` antes de continuar — este script no exporta, sube ni publica nada.

---

## Paso 2 — Auditar el portal origen

```bash
python scripts/audit.py
```

Genera `data/output/inventario_con_carpetas.csv` con **todo** el contenido
accesible por la cuenta `ORIGEN_*` (todos los Types, no solo Feature
Service). Revisa en el resumen cuantos items/Types/carpetas encontro.

---

## Paso 3 — Preparar el inventario de migracion

Hay dos modos. Elige uno (no hace falta ejecutar ambos):

### Modo manual (copia todo, curas a mano en el Paso 4)

```bash
python scripts/prepare.py
```

Copia **todo** el inventario auditado a `data/input/inventario_migracion.csv`
sin filtrar nada. En el Paso 4 tendras que editar el CSV a mano.

### Modo automatico — filtrar usando `app.arcgis_upload` (recomendado)

Genera `inventario_migracion.csv` ya filtrado: **solo** los items cuyo
`layer_id`/`service_url` esten registrados en `app.arcgis_upload`. Si algun
item de la tabla no aparecio en el audit (por ejemplo, por ser privado de
otra cuenta), este modo intenta resolverlo con un lookup directo al portal
origen antes de darlo por perdido — esto reemplaza el paso manual del CSV.

```bash
# Camino A — acceso directo a Postgres
python scripts/prepare.py --db-dsn

# Camino B — CSV manual de arcgis_upload
python scripts/prepare.py --arcgis-upload-csv data/input/arcgis_upload_export.csv
```

Flags adicionales (ambos caminos):

| Flag | Uso |
|---|---|
| `--only-system-account` | Solo filas `is_system_account = true` (requiere `--db-dsn`) |
| `--join-key service_url` | Correlacionar por `service_url` en vez de `layer_id` |

Si ya existe `data/input/inventario_migracion.csv` de una corrida anterior,
agrega `--force` a cualquiera de los comandos de arriba para regenerarlo.

### Que revisar (modo automatico)

El resumen en consola muestra:

- `Filas en arcgis_upload`: total de registros considerados.
- `Encontradas en audit`: ya estaban en `inventario_con_carpetas.csv`.
- `Resueltas por lookup directo en origen`: no estaban en el audit, pero se
  encontraron consultando el item directamente (como paso con `migration_test`
  al cambiar `ORIGEN_USER`).
- `Sin resolver`: no se encontraron ni en el audit ni por lookup directo —
  revisar `data/output/sin_match_inventario_db.csv` **antes de seguir**,
  puede ser un `layer_id` invalido, un item borrado, o credenciales de
  origen sin acceso a ese item.

---

## Paso 4 — Curar el inventario (manual, opcional)

Si usaste el **modo automatico** del Paso 3, `inventario_migracion.csv` ya
viene filtrado — puedes saltar directo al Paso 5, o abrir el CSV igual para
revisar/ajustar filas puntuales antes de migrar.

Si usaste el **modo manual** del Paso 3 (copia completa sin filtrar):

1. Abre `data/input/inventario_migracion.csv`.
2. **Elimina las filas** de items que NO quieras migrar en esta corrida.
3. Guarda el archivo.

---

## Paso 5 — Migracion masiva

```bash
python scripts/migrate.py
```

- Progreso en consola y en `logs/migrate_*.log`.
- Estado persistente en `state/migration_state.db` (permite reanudar).
- Mapeo item por item en `data/output/mapeo_migracion.csv`.

### Reanudar / reintentar

```bash
python scripts/migrate.py                 # reanuda, omite los 'success'
python scripts/migrate.py --retry-errors   # reintenta los que fallaron
```

Repite este paso hasta que el resumen diga `Pendientes: 0`.

---

## Paso 6 — Reporte final

```bash
python scripts/report.py
```

Resumen de total/exitos/errores/pendientes. Genera
`data/output/errores_migracion.csv` (solo los `ERROR`, no los `SKIP`).

**Antes de seguir**: revisa que `Exitos acumulados` sea el numero esperado
y que `Errores acumulados` sea 0 (o que los errores restantes sean
aceptables / ya investigados).

---

## Paso 7 — Validar la correlacion con `app.arcgis_upload`

Confirma, contra el portal **origen**, que la clave de correlacion
(`layer_id` = itemId de origen, `service_url` = url de origen) se cumple
antes de confiar en el `.sql` del Paso 8.

### Camino A — Acceso directo a Postgres

```bash
python scripts/validate_db_correlation.py --db-dsn
```

### Camino B — CSV manual de `app.arcgis_upload`

```bash
python scripts/validate_db_correlation.py --arcgis-upload-csv data/input/arcgis_upload_export.csv
```

El CSV debe tener las columnas: `id, client_code, service_name,
item_type_code, layer_id, service_url`.

### Que revisar (ambos caminos)

Abre `data/output/validacion_correlacion.csv` y el resumen en consola:

- Si **predominan `MATCH`**: la clave de correlacion es correcta, continua
  al Paso 8 con el mismo camino (A o B).
- Si aparecen `MISMATCH` o `NOT_FOUND`: **detente** y revisa esas filas
  puntualmente antes de generar el `.sql` (puede ser una cuenta de origen
  distinta, un item ya borrado, o un `layer_id` que no corresponde al
  itemId de origen). Ver [DB_CORRELATION.md](DB_CORRELATION.md).

---

## Paso 8 — Generar el `.sql` de actualizacion

Cruza `data/output/mapeo_migracion.csv` (filas `EXITO`) contra
`app.arcgis_upload` y escribe el `UPDATE` listo para revisar.

### Camino A

```bash
python scripts/generate_db_update.py --db-dsn
```

### Camino B

```bash
python scripts/generate_db_update.py --arcgis-upload-csv data/input/arcgis_upload_export.csv
```

### Flags utiles (ambos caminos)

| Flag | Uso |
|---|---|
| `--only-system-account` | Solo filas `is_system_account = true` (requiere `--db-dsn`) |
| `--join-key service_url` | Alternativa si el Paso 7 mostro que la clave real es `service_url` en vez de `layer_id` |
| `--output <ruta>` | Cambiar donde se escribe el archivo (default `data/output/update_arcgis_upload.sql`, o `data/output/m{timestamp}_update_arcgis_upload.php` con `--format yii`) |
| `--no-token` | No tocar `access_token`/`username`/`token_expires_at` (solo `service_url`+`layer_id`) |
| `--format yii` | En vez del `.sql`, generar **solo** un migration de Yii (`.php`) — ver seccion abajo |

### Token de origen anulado (`access_token` / `token_expires_at`)

El `access_token` guardado hoy en `arcgis_upload` es del portal **ORIGEN**
y ya no sirve una vez el servicio esta migrado a DESTINO. Salvo
`--no-token`, cada `UPDATE` pone `access_token = ''`,
`token_expires_at = ''` (cadena vacia: las columnas son `NOT NULL`) y `username = DESTINO_USER`. Este script **no
genera ni embebe** un token: el archivo no es un secreto. El token real
de DESTINO lo escribe despues un comando PHP en el proyecto `fdsu` (ver
[DB_CORRELATION.md](DB_CORRELATION.md)).

### Alternativa: generar un migration de Yii (`--format yii`)

Si vas a aplicar el cambio en el proyecto `fdsu` (Yii 1.1), pedi
directamente un migration en vez del `.sql`:

```bash
# Camino A
python scripts/generate_db_update.py --db-dsn --format yii

# Camino B
python scripts/generate_db_update.py --arcgis-upload-csv data/input/arcgis_upload_export.csv --format yii
```

Con `--format yii` el script **no** escribe el `.sql`: en su lugar deja
un `.php` en `data/output/` (nombre `m{YYMMDD}_{HHMMSS}_update_arcgis_upload.php`,
convencion de Yii), con los mismos `UPDATE` que generaria el `.sql` pero
usando `Yii::app()->dbWrite->createCommand(...)->execute();` por fila
(con contador/`echo` de progreso) y `(new CacheDbSchema)->invalidate(['arcgis_upload']);`
al final — igual que las migraciones de datos reales en
`fdsu/console/migrations/`. El Paso 9 cambia segun el formato elegido.

### Que revisar

- `data/output/update_arcgis_upload.sql` (default) o `data/output/m..._update_arcgis_upload.php`
  (con `--format yii`): un `UPDATE app.arcgis_upload ...` por cada fila
  emparejada (`access_token` y `token_expires_at` en `''`, salvo `--no-token`).
- `data/output/sin_match_arcgis_upload.csv` (si existe): filas `EXITO` del
  mapeo que **no** encontraron fila en `arcgis_upload` — revisar antes de
  continuar, no se pierden en silencio.

Este script **no ejecuta nada** contra la base de datos; solo lee (para
emparejar) y escribe el archivo.

---

## Paso 9 — Entregar y ejecutar el resultado

### Si usaste el formato `.sql` (default)

1. Entrega `data/output/update_arcgis_upload.sql` al equipo de
   datos/DBA (o ejecutalo tu mismo si tienes permiso de escritura).
2. Revisa el contenido antes de correrlo — son `UPDATE` por `id` de
   `arcgis_upload`, dentro de una transaccion `BEGIN;`/`COMMIT;`.
   `access_token` y `token_expires_at` quedan en `''`.
3. Ejecutalo contra la base de datos real (fuera de este toolkit, p. ej.
   con `psql` o el cliente que use el equipo de datos).
4. Despues, el comando PHP de `fdsu` escribe el token de DESTINO.

### Si usaste `--format yii`

1. Revisa el `.php` generado en `data/output/` (misma logica/datos que el
   `.sql`: token y expiracion en `''`).
2. Copialo a `console/migrations/` dentro del repo `fdsu`.
3. Desde la raiz de `fdsu`, ejecuta manualmente:
   ```bash
   php console/yiic migrate
   ```
4. Despues, el comando PHP de `fdsu` escribe el token de DESTINO.

Este toolkit **no copia ni ejecuta** el `.php` en `fdsu`; ese paso lo
hace el usuario/DBA manualmente, igual que con el `.sql`.

---

## Paso 10 — Verificacion final

1. Vuelve a consultar `app.arcgis_upload` para las filas actualizadas:
   `service_url` y `layer_id` deben apuntar ahora al portal **destino**.
2. Abre uno de los `URL_Nueva` del mapeo en el navegador (o
   `gis_destino.content.get(ID_Nuevo)`) y confirma que el Feature Service
   responde en destino.
3. Si todo esta correcto, esta guia queda como las instrucciones de
   ejecucion oficiales para la siguiente corrida de produccion.

---

## Anexo — Limpieza de items de prueba en destino

Si durante las pruebas se crearon items de mas en el portal **destino**
(por ejemplo corridas repetidas de este flujo) y quieres dejarlo limpio
antes de la corrida real:

```bash
# Ver que se borraria en una carpeta de destino, sin borrar
python scripts/cleanup_destino.py --folder <CARPETA_DESTINO> --dry-run

# Borrar todo lo de esa carpeta (y la carpeta si queda vacia)
python scripts/cleanup_destino.py --folder <CARPETA_DESTINO>

# Borrar un item puntual por itemId (p. ej. un item creado manualmente)
python scripts/cleanup_destino.py --item-id <itemId_en_destino>
```

Siempre opera sobre `DESTINO_*` de `.env`; nunca toca el portal origen.
Util tambien para limpiar `data/output/*` y `state/*.db` locales entre
pruebas con `cleanup_local.py` (Paso 0.1).

---

## Referencia cruzada

- Detalle tecnico de cada script y fase: [WORKFLOW.md](WORKFLOW.md)
- Por que cambian las URLs/IDs al migrar: [URL_PRESERVATION.md](URL_PRESERVATION.md)
- Estructura de `app.arcgis_upload` y la hipotesis de correlacion: [DB_CORRELATION.md](DB_CORRELATION.md)
