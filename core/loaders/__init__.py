"""Единая точка входа загрузки данных: load_data(path) -> list[dict]."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import AppError
from core.loaders.csv_loader import load_csv
from core.loaders.json_loader import load_json


def load_data(
    path: Path,
    config: dict[str, Any] | None = None,
    json_root: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Определить формат по расширению и вернуть список записей.

    Второй элемент — служебные сведения (кодировка CSV, движок и т.п.) для вывода пользователю.
    Остальной код не должен зависеть от источника данных.
    """
    config = config or {}
    suffix = path.suffix.lower()
    meta: dict[str, str] = {"format": suffix.lstrip(".").upper()}

    if suffix == ".csv":
        records, encoding, delimiter, engine = load_csv(path, config)
        meta.update(
            {
                "encoding": encoding,
                "delimiter": delimiter,
                "engine": engine,
            }
        )
        return records, meta

    if suffix == ".json":
        root = json_root if json_root is not None else str(config.get("json_root", "auto"))
        records, skipped = load_json(path, json_root=root)
        meta["skipped"] = str(skipped)
        return records, meta

    raise AppError(
        f"Неподдерживаемый формат файла {path.name}. Ожидаются CSV или JSON."
    )
