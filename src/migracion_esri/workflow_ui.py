import logging
from dataclasses import dataclass


@dataclass
class WorkflowSummary:
    script: str
    lines: list[str]
    errors: int = 0
    next_command: str = ""
    next_hint: str = ""


def _log_to_file_only(logger: logging.Logger, level: int, text: str) -> None:
    """Write to FileHandler(s) only — avoids duplicating print() on console."""
    record = logger.makeRecord(
        logger.name,
        level,
        "(workflow_ui)",
        0,
        "\n%s",
        (text,),
        None,
    )
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.emit(record)


def print_summary(summary: WorkflowSummary, logger=None) -> None:
    block = [
        "=" * 50,
        f" RESUMEN - {summary.script}",
        "-" * 50,
        *summary.lines,
    ]
    if summary.errors:
        block.append(f" Errores: {summary.errors} (detalle en log)")
    block.extend(["=" * 50])
    if summary.next_command:
        block.append(f" NEXT -> {summary.next_command}")
        if summary.next_hint:
            block.append(f"        {summary.next_hint}")
        block.append("=" * 50)

    text = "\n".join(block)
    print(text)
    if logger:
        _log_to_file_only(logger, logging.INFO, text)


def print_failure_summary(script: str, error: str, logger=None) -> None:
    block = [
        "=" * 50,
        f" RESUMEN - {script} (FALLIDO)",
        "-" * 50,
        f" Error: {error}",
        "=" * 50,
        " Corrija el problema antes de continuar.",
        "=" * 50,
    ]
    text = "\n".join(block)
    print(text)
    if logger:
        _log_to_file_only(logger, logging.ERROR, text)
