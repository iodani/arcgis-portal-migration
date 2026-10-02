# URL and item ID preservation

## Question

Can we copy Feature Services to the new portal and **keep the same REST URL / item ID**, so we skip updating our application database?

## Short answer

**No** — not for a real cutover between ArcGIS Online organizations (or AGOL → Location Platform org). Independent hosted data always gets a **new item ID** and a **new Feature Service URL**. The mapping file `mapeo_migracion.csv` remains required.

## Why Assistant seemed to keep the same URL

ArcGIS Assistant (and `clone_items(copy_data=False)`) can create a **reference / simple copy**: a new portal item whose `url` still points at the **source** org’s hosted service (`services*.arcgis.com/...` of the origin).

That looks like “same URL,” but:

- Data ownership stays on the **source** portal.
- Turning off or deleting the source service breaks destination consumers.
- It is **not** a migration suitable for leaving ArcGIS Online for a new portal.

A **full copy** (Assistant full copy, `clone_items(copy_data=True)`, or this toolkit’s FGDB → publish path) creates a new hosted service on the destination → **new URL**.

## Empirical check (2026-10-01)

Controlled probe on source Feature Service `EvacuationRoutes` (`d0647baa02f0462e9856f648bc78750e`):

| | Item ID | FeatureServer URL |
|--|---------|-------------------|
| Source (fdsu.maps.arcgis.com) | `d0647baa...` | `https://services8.arcgis.com/jNUIWEZv9aaHqUtJ/.../FeatureServer` |
| Destination after `clone_items(copy_data=False)` | **new** `cf75f1c0...` | **identical** to source URL (org host `jNUIWEZv9aaHqUtJ`) |

Conclusion: **same URL ⇒ reference to source hosting**, not independent data on the destination org. The destination item ID still changes; only the service URL is reused because it still points at the origin.

This toolkit’s production path (`FeatureServiceDriver`: export FGDB → publish) intentionally creates an independent service → **new URL**, which is why `mapeo_migracion.csv` exists.

## What this toolkit does

`FeatureServiceDriver` always:

1. Exports File Geodatabase on source  
2. Uploads to destination  
3. Publishes a new hosted Feature Service  

→ returns `id_nuevo` / `url_nueva` for `mapeo_migracion.csv`.

There is no supported AGOL flag to assign a custom hosted service URL or to preserve AGOL item IDs across orgs. `preserve_item_id` is **Enterprise-only** and still does not keep the FeatureServer host/path when republishing.

## How to verify on a single test item

1. Open the destination item created by Assistant.  
2. Compare its `url` to the source item’s `url`.  
   - **Identical host/path** → reference copy (same URL, source still owns data).  
   - **Different `servicesN` or service name** → real copy (new URL; mapeo needed).  
3. Compare with a row in `mapeo_pilot.csv` / `mapeo_migracion.csv` from this tool: destination URL will differ by design.

## Business conclusion

For “migrate data to the new portal and keep the app working,” plan for:

1. Batch migration (this tool)  
2. Apply `mapeo_migracion.csv` to the database  
3. Point app config at the new portal  

Skipping the DB update only works if you accept **reference copies** — which does not meet the cutover goal.
