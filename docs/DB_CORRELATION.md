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
| `item_type_code` | varchar | Codigo del tipo de capa |
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

Esta hipotesis debe validarse con datos del entorno donde se ejecutara la
migracion. Para eso existe `validate_db_correlation.py`: usa las
credenciales configuradas en `.env` para resolver cada `layer_id` como item
del portal y comparar su URL con `service_url`.

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
| `--format` | `sql` | `sql` (default) genera el `.sql`; `yii` genera **solo** un migration de Yii (`.php`), ver seccion abajo |
| `--output` | `data/output/update_arcgis_upload.sql` (o `data/output/m{timestamp}_update_arcgis_upload.php` con `--format yii`) | Ruta del archivo generado |
| `--no-token` | `false` | No tocar `access_token`/`username`/`token_expires_at` (solo `service_url` + `layer_id`) |

Salida:

- `data/output/update_arcgis_upload.sql`: un `UPDATE` por cada fila de
  `arcgis_upload` que hizo match, envuelto en `BEGIN;` / `COMMIT;`.
- `data/output/sin_match_arcgis_upload.csv`: filas `EXITO` del mapeo que
  **no** encontraron fila correspondiente en `arcgis_upload` (para que no
  se pierdan en silencio).

Ejemplo ilustrativo de UPDATE generado (valores ficticios):

```sql
UPDATE app.arcgis_upload
SET service_url = '<DESTINATION_FEATURE_SERVICE_URL>',
    layer_id    = '<DESTINATION_ITEM_ID>'
WHERE id = <DATABASE_ROW_ID>;
```

### Token de origen anulado (`access_token` / `token_expires_at`)

El `access_token` que hoy tiene `arcgis_upload` fue emitido contra el
**portal ORIGEN**: una vez migrado el Feature Service a DESTINO, ese token
no sirve. Este script **no genera ni embebe** un token nuevo (el archivo
no queda como secreto). Salvo `--no-token`, cada `UPDATE` deja:

- `username = DESTINO_USER` (cuenta de `.env`)
- `access_token = ''`
- `token_expires_at = ''`

Cadena vacia, no `NULL`: ambas columnas son `NOT NULL`.

El token real de DESTINO lo escribe despues un comando aparte en el
proyecto `fdsu`, fuera de este toolkit.

```sql
UPDATE app.arcgis_upload
SET service_url = '<DESTINATION_FEATURE_SERVICE_URL>',
    layer_id    = '<DESTINATION_ITEM_ID>',
    username    = '<DESTINATION_USERNAME>',
    access_token = '',
    token_expires_at = ''
WHERE id = <DATABASE_ROW_ID>;
```

### Alternativa: generar un migration de Yii en vez del `.sql` (`--format yii`)

Si el equipo de datos trabaja con el proyecto `fdsu` (Yii 1.1), se puede
pedir directamente un migration `CDbMigration` en vez del `.sql`:

```bash
python scripts/generate_db_update.py --db-dsn --format yii
```

Con `--format yii`, el script **no** escribe el `.sql`: en su lugar
escribe un `.php` en `data/output/`, nombrado
`m{YYMMDD}_{HHMMSS}_update_arcgis_upload.php` (convencion de nombres de
Yii), listo para que lo revise, lo copie a `console/migrations/` dentro
del repo `fdsu`, y lo ejecute manualmente con:

```bash
php console/yiic migrate
```

El contenido replica exactamente los mismos `UPDATE` que generaria el
`.sql` (misma logica de match; `access_token` y `token_expires_at` en
`''` salvo `--no-token`, porque las columnas son `NOT NULL`), pero usando los patrones reales de
`fdsu/console/migrations/`:

- `Yii::app()->dbWrite->createCommand('<sql>')->execute();` por cada fila
  emparejada, con contador de progreso (`$total`/`$updated`) y `echo` por
  fila.
- `(new CacheDbSchema)->invalidate(['arcgis_upload']);` al final de
  `up()`, para invalidar el cache de esquema de Yii sobre esa tabla —
  patron muy comun en ese repo tras modificar datos/columnas.
- `down()` con `echo "... no soporta rollback ...\n"; return false;`,
  ya que esta migracion no es reversible (no se conserva el estado
  anterior de `access_token`/`username`).

Ejemplo (`--format yii`, token anulado):

```php
<?php

// La clase y el nombre de archivo siguen la convencion de Yii:
// m{YYMMDD}_{HHMMSS}_update_arcgis_upload.
class mYYMMDD_HHMMSS_update_arcgis_upload extends CDbMigration
{
    public function up()
    {
        $total = 1;
        $updated = 0;

        Yii::app()->dbWrite->createCommand("
		UPDATE arcgis_upload
		SET
			service_url = '<DESTINATION_FEATURE_SERVICE_URL>',
			layer_id = '<DESTINATION_ITEM_ID>',
			username = '<DESTINATION_USERNAME>',
			access_token = '',
			token_expires_at = ''
		WHERE
			id = <DATABASE_ROW_ID>
	")
	->execute();
        $updated++;
        echo date('Y-m-d H:i:s') . "\n" . "Update {$updated}/{$total}" . "\n\n";

        (new CacheDbSchema)->invalidate(['arcgis_upload']);

        return true;
    }

    public function down()
    {
        echo "Esta migracion no soporta rollback.\n";
        return false;
    }
}
```

Igual que con el `.sql`: este toolkit **no copia ni ejecuta** el `.php`
en el repo `fdsu`. El token de DESTINO lo escribe despues un comando
aparte en ese proyecto.

### Importante: nada se ejecuta automaticamente

Ambos scripts son de **solo lectura** sobre la base de datos (`SELECT`
unicamente, incluso en modo `--db-dsn` se abre la conexion con
`readonly=True`). El archivo final (`.sql` o `.php` con `--format yii`)
debe ser revisado y ejecutado manualmente por el equipo de datos/DBA,
igual que el resto de este toolkit no actualiza bases de datos
directamente (ver
[WORKFLOW.md](WORKFLOW.md), Fase 7).
