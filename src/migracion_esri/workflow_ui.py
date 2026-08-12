from dataclasses import dataclass
from typing import Callable


@dataclass
class WorkflowSummary:
    script: str
    lines: list[str]
    errors: int = 0
    next_command: str = ""
    next_hint: str = ""


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
        logger.info("\n%s", text)


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
        logger.error("\n%s", text)
