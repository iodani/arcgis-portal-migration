"""Helpers genericos para generar un migration de Yii (CDbMigration) en PHP.

No contiene logica de negocio de app.arcgis_upload: solo las piezas
mecanicas (nombre de clase/archivo, escape de strings PHP, y el
ensamblado del .php) que usa scripts/generate_db_update.py cuando se
invoca con --format yii.
"""

import re
import time


def php_quote(value) -> str:
    """Escapa un valor para usarlo como literal PHP de comillas simples.

    Mismo principio que _sql_quote() en generate_db_update.py, pero para
    PHP: dentro de un string '...' solo \\ y ' son especiales (los saltos
    de linea reales se mantienen literales, igual que en las migraciones
    reales de fdsu que embeben SQL multilinea).
    """
    text = "" if value is None else str(value)
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def php_escape_double_quoted(text: str) -> str:
    """Escapa texto para insertarlo DENTRO de un string PHP de comillas
    dobles ("..."), sin agregar las comillas que lo envuelven.

    Dentro de "..." son especiales \\, $ (interpolacion de variables) y "
    (cierra el string); los saltos de linea reales se mantienen literales
    -- igual que el SQL multilinea embebido en las migraciones reales de
    fdsu (`Yii::app()->dbWrite->createCommand("...")`).
    """
    return text.replace("\\", "\\\\").replace("$", "\\$").replace('"', '\\"')


def build_migration_class_name(description: str, when: time.struct_time | None = None) -> str:
    """Devuelve el nombre de clase/archivo Yii: m{YYMMDD}_{HHMMSS}_{description}.

    Usa hora local (igual que el resto de timestamps de este toolkit).
    """
    when = when or time.localtime()
    stamp = time.strftime("%y%m%d_%H%M%S", when)
    safe_description = re.sub(r"[^a-z0-9_]+", "_", description.strip().lower()).strip("_")
    if not safe_description:
        safe_description = "migration"
    return f"m{stamp}_{safe_description}"


def render_cdb_migration(
    class_name: str,
    docblock_lines: list[str],
    up_body: str,
    down_body: str,
) -> str:
    """Arma el .php completo de una migracion CDbMigration.

    `up_body` y `down_body` ya deben venir indentados/formateados como
    cuerpo de metodo (sin la firma `public function up() { ... }`).
    """
    docblock = "\n".join(f" * {line}" if line else " *" for line in docblock_lines)
    return (
        "<?php\n"
        "\n"
        "/**\n"
        f"{docblock}\n"
        " */\n"
        f"class {class_name} extends CDbMigration\n"
        "{\n"
        "    public function up()\n"
        "    {\n"
        f"{up_body}\n"
        "    }\n"
        "\n"
        "    public function down()\n"
        "    {\n"
        f"{down_body}\n"
        "    }\n"
        "}\n"
    )
