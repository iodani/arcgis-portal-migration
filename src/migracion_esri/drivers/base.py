from dataclasses import dataclass


@dataclass
class MigrationResult:
    id_nuevo: str
    url_nueva: str


class SkipMigration(Exception):
    """Raised when an item is intentionally not migrated (registered as SKIP)."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)
