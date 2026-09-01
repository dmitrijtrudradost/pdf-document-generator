"""Кроссплатформенное открытие файла и папки в системной программе."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_path(path: Path) -> str | None:
    """Открыть файл или папку. Ошибка не прерывает работу — возвращает предупреждение."""
    target = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", target], check=False)
        else:
            subprocess.run(["xdg-open", target], check=False)
    except OSError as exc:
        return f"Не удалось открыть {path}: {exc}"
    return None


def open_results(
    created: list[Path],
    output_dir: Path,
    *,
    auto_open: bool,
    auto_open_limit: int,
    no_open: bool,
    open_folder: bool,
) -> list[str]:
    """Открыть готовые PDF или папку вывода согласно правилам ТЗ."""
    warnings: list[str] = []
    if no_open or not created:
        return warnings
    if not auto_open and not open_folder:
        return warnings

    if open_folder or len(created) > auto_open_limit:
        warn = open_path(output_dir)
        if warn:
            warnings.append(warn)
        return warnings

    for path in created:
        warn = open_path(path)
        if warn:
            warnings.append(warn)
    return warnings
