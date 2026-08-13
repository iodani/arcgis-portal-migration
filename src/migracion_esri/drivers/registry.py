"""Type ArcGIS → driver, fase, and skip rules."""

DRIVER_FEATURE_SERVICE = "feature_service"
DRIVER_CLONE_ITEMS = "clone_items"
DRIVER_SKIP = "skip"

FASE_SKIP = 0
FASE_DATA = 1
FASE_REFERENCES = 2

FEATURE_SERVICE_TYPE = "Feature Service"

SKIP_TYPES = frozenset({
    "API Key",
    "Administrative Report",
    "Geocoding Service",
    "Hub Initiative",
    "Hub Site Application",
})

PHASE_2_TYPES = frozenset({
    "Application",
    "Dashboard",
    "Form",
    "Group Layer",
    "Map Area",
    "Web Experience",
    "Web Map",
    "Web Mapping Application",
    "Web Scene",
})


def get_driver_name(item_type: str) -> str:
    if item_type in SKIP_TYPES:
        return DRIVER_SKIP
    if item_type == FEATURE_SERVICE_TYPE:
        return DRIVER_FEATURE_SERVICE
    return DRIVER_CLONE_ITEMS


def get_fase(item_type: str) -> int:
    if item_type in SKIP_TYPES:
        return FASE_SKIP
    if item_type in PHASE_2_TYPES:
        return FASE_REFERENCES
    return FASE_DATA
