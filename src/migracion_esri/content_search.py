"""Portal content search helpers (no Item._hydrate)."""

PAGE_SIZE = 100


def item_value(item, key: str, default=None):
    """Read search metadata without triggering Item._hydrate() API calls."""
    try:
        if key in item:
            return item[key]
    except (KeyError, TypeError):
        pass
    return default


def fetch_all_items(gis, logger, page_size: int = PAGE_SIZE):
    org_id = gis.properties.id
    query = f"orgid:{org_id}"
    items = []
    start = 1
    while True:
        response = gis.content.advanced_search(
            query=query,
            max_items=page_size,
            start=start,
        )
        if not isinstance(response, dict):
            break
        batch = response.get("results") or []
        if not batch:
            break
        items.extend(batch)
        logger.info("Pagina start=%d: +%d items (total %d)", start, len(batch), len(items))
        next_start = response.get("nextStart", -1)
        if len(batch) < page_size or next_start in (-1, None):
            break
        start = next_start
    return items
