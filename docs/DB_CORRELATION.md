# Correlacion `mapeo_migracion.csv` -> `app.arcgis_upload`

## Objetivo

Despues de migrar un Feature Service con `migrate.py`, el resultado
(`data/output/mapeo_migracion.csv`) debe reflejarse en la base de datos de
la plataforma (`app.arcgis_upload`) para que la aplicacion apunte al
servicio **nuevo** (destino) en lugar del **viejo** (origen).

> Para ejecutar el flujo completo paso a paso (instalacion, limpieza,
> migracion y actualizacion de BD) ver [GUIA_EJECUCION.md](GUIA_EJECUCION.md).
> Este documento es la referencia tecnica detras de esos pasos.

Este documento explica la estructura real de la tabla, la hipotesis de
correlacion y como generar (sin ejecutar) el SQL de actualizacion.

## Estructura de `app.arcgis_upload`

Columnas relevantes (schema `app`, Postgres):

| Columna | Tipo | Uso |
|---|---|---|
| `id` | integer | PK interna de la tabla |
| `client_code` | varchar | Cliente propietario del servicio |
| `service_name` | varchar | Nombre legible del Feature Service |
| `item_type_code` | varchar | Tipo de capa (`hydrants`, `addresses`, `preplan`, ...) |
| `service_url` | text | URL raiz del FeatureServer (equivalente a `encodedServiceURL` de Esri) |
| `layer_id` | text | `itemId` del portal (GUID del item de contenido en ArcGIS Online) — **no** es el indice de capa dentro del FeatureServer |
| `is_system_account` | boolean | Si la credencial usada para publicar es la cuenta de sistema |

Origen de estos dos campos en el proyecto `fdsu` (`ArcgisUploadController::actionCreate`):

```php
$arcGisUpload->service_url = $featureService->encodedServiceUrl;
$arcGisUpload->layer_id    = $featureService->itemId;
```

Es decir, ambos campos se copian **una sola vez** de la respuesta de
`createService` en ArcGIS Online, en el momento en que el registro se crea.

## Equivalencia con el resultado de este toolkit

`FeatureServiceDriver.migrate()` (ver
[`feature_service.py`](../src/migracion_esri/drivers/feature_service.py))
hace export FGDB -> upload -> publish y devuelve:

```python
MigrationResult(id_nuevo=capa_publicada.id, url_nueva=capa_publicada.url or "")
```

| `arcgis.gis.Item` | `app.arcgis_upload` | `mapeo_migracion.csv` |
|---|---|---|
| `capa_publicada.id` (GUID del item publicado) | `layer_id` | `ID_Nuevo` |
| `capa_publicada.url` (raiz del FeatureServer, sin indice de capa) | `service_url` | `URL_Nueva` |

## Hipotesis de correlacion (clave de JOIN)

Para saber **que fila** de `arcgis_upload` corresponde a **que fila** del
mapeo, se necesita una clave presente en ambos lados. `arcgis_upload` no
guarda historico de valores "viejos": solo tiene el valor vigente.

Hipotesis adoptada por defecto: **antes de migrar**, el servicio vigente en
produccion es el del portal origen, por lo que:

```
arcgis_upload.layer_id    (antes de migrar) == mapeo.ID_Viejo   (itemId en origen)
arcgis_upload.service_url (antes de migrar) == mapeo.URL_Vieja (url en origen)
```

Esto es consistente con la unica fila observada en el ambiente de
desarrollo (`id=45`, `client_code=ALEXANDRIA_CITY`, `item_type_code=hydrants`,
`layer_id=e7cc59e1ab764e9fa85dc571035f4cb5`), cuyo `service_url` todavia
apunta al org de **origen** (`services8.arcgis.com/jNUIWEZv9aaHqUtJ/...`,
el mismo org ID que `ORIGEN_URL`/`ORIGEN_USER` en `.env`).

No se pudo confirmar de forma anonima contra la REST API publica de Esri
(el item es privado -> `403`, el servicio exige token -> `499`), por eso
existe `validate_db_correlation.py`: usa las credenciales de `.env`
(`ORIGEN_USER`/`ORIGEN_PASS`) para resolver cada `layer_id` como item de
portal y comparar su `url` real contra `service_url`.

**Antes de confiar en el `.sql` generado por `generate_db_update.py`,
ejecute `validate_db_correlation.py` y revise que la mayoria de filas sea
`MATCH`.** Si predominan `MISMATCH`, la clave de correlacion real en su
entorno es otra (por ejemplo, basada en `client_code` + `item_type_code`
curado manualmente) y no debe usarse el join automatico.

## Uso

### Fase 0 — Validar la hipotesis

```bash
python scripts/validate_db_correlation.py --db-dsn
# o, sin acceso directo a la BD:
python scripts/validate_db_correlation.py --arcgis-upload-csv data/input/arcgis_upload_export.csv
```

Salida: `data/output/validacion_correlacion.csv` con un resultado por fila
(`MATCH`, `MISMATCH`, `NOT_FOUND`, `EMPTY_LAYER_ID`, `ERROR`).

### Fase 2 — Generar el SQL

```bash
python scripts/generate_db_update.py --db-dsn
# o:
python scripts/generate_db_update.py --arcgis-upload-csv data/input/arcgis_upload_export.csv
```

Flags relevantes:

| Flag | Default | Uso |
|---|---|---|
| `--mapeo` | `data/output/mapeo_migracion.csv` | CSV de mapeo a usar |
| `--db-dsn` | — | Conexion directa a Postgres (solo lectura) usando `PGDSN`/`PGSCHEMA` en `.env` |
| `--arcgis-upload-csv` | — | Alternativa sin credenciales de BD: CSV exportado manualmente con columnas `id, client_code, service_name, item_type_code, layer_id, service_url` |
| `--join-key` | `layer_id` | `layer_id` (default) o `service_url` |
| `--only-system-account` | `false` | Filtra solo filas `is_system_account = true` (requiere `--db-dsn`) |
| `--output` | `data/output/update_arcgis_upload.sql` | Ruta del `.sql` generado |
| `--no-token` | `false` | No generar/incluir `access_token` nuevo (solo `service_url` + `layer_id`) |
| `--token-expiration-minutes` | `TOKEN_EXPIRATION_MINUTES` en `.env`, o `60` | Expiracion (minutos) del token nuevo pedido para DESTINO |

Salida:

- `data/output/update_arcgis_upload.sql`: un `UPDATE` por cada fila de
  `arcgis_upload` que hizo match, envuelto en `BEGIN;` / `COMMIT;`.
- `data/output/sin_match_arcgis_upload.csv`: filas `EXITO` del mapeo que
  **no** encontraron fila correspondiente en `arcgis_upload` (para que no
  se pierdan en silencio).

Ejemplo de UPDATE generado:

```sql
-- migration test | client_code=ALEXANDRIA_CITY | item_type_code=hydrants | id=45
UPDATE app.arcgis_upload
SET service_url = 'https://services7.arcgis.com/XXXX/arcgis/rest/services/migration_test/FeatureServer',
    layer_id    = '9ffa9ced3fdc46248a4f3700ae8cc685'
WHERE id = 45;
```

### Token nuevo para DESTINO (`access_token` / `username` / `token_expires_at`)

El `access_token` que hoy tiene `arcgis_upload` fue emitido contra el
**portal ORIGEN**: una vez migrado el Feature Service a DESTINO, ese token
no sirve para operar sobre el servicio nuevo. Por eso, salvo que se pase
`--no-token`, `generate_db_update.py` ademas:

1. Pide **un** token nuevo (REST `generateToken`, no la libreria `arcgis`)
   para la cuenta `DESTINO_USER`/`DESTINO_PASS` (de `.env`) contra
   `DESTINO_URL`. Se pide una sola vez por corrida (no una vez por fila):
   todas las filas migradas quedan con el mismo `access_token`, porque
   todas se publicaron con la misma cuenta de destino.
2. Agrega al `UPDATE` de cada fila emparejada: `username = DESTINO_USER`
   y `access_token = '<token nuevo>'` (comillas simples, igual manejo que
   `service_url`/`layer_id`) y `token_expires_at = <epoch>` (numerico, sin
   comillas — ver punto 4).
3. La expiracion default es **60 minutos (1 hora)**, configurable con
   `TOKEN_EXPIRATION_MINUTES` en `.env` o `--token-expiration-minutes`.
4. `token_expires_at` se escribe en **formato numerico** (epoch Unix en
   segundos, ej. `1827843908`), sin comillas -- igual que lo espera la
   columna en `app.arcgis_upload`. El comentario arriba del `UPDATE` en el
   `.sql` incluye tambien la hora legible en UTC, solo como referencia.

Ejemplo de UPDATE con token:

```sql
UPDATE app.arcgis_upload
SET service_url = 'https://services7.arcgis.com/XXXX/arcgis/rest/services/migration_test/FeatureServer',
    layer_id    = '9ffa9ced3fdc46248a4f3700ae8cc685',
    username    = 'it-esri-admin',
    access_token = 'AbC123...tokenReal...',
    token_expires_at = 1827843908
WHERE id = 45;
```

**Advertencia de seguridad:** con esta opcion activa (default), el `.sql`
generado contiene un token valido de ArcGIS — tratelo como un secreto:
no lo adjunte en tickets/chats, no lo deje en el repo, y bórrelo despues
de aplicarlo. Ademas, el token expira: el `.sql` debe aplicarse **antes**
de la hora de expiracion indicada en el encabezado del archivo y en el
resumen que imprime el script, o quedara con un `access_token` ya vencido.

### Importante: nada se ejecuta automaticamente

Ambos scripts son de **solo lectura** sobre la base de datos (`SELECT`
unicamente, incluso en modo `--db-dsn` se abre la conexion con
`readonly=True`). La generacion del token nuevo es una llamada de
**solo lectura/autenticacion** contra la REST API de ArcGIS (no modifica
nada en los portales); el `.sql` final —con o sin token— debe ser
revisado y ejecutado manualmente por el equipo de datos/DBA, igual que el
resto de este toolkit no actualiza bases de datos directamente (ver
[WORKFLOW.md](WORKFLOW.md), Fase 7).
