"""Чтение и создание config.json."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from core import AppError

DEFAULT_CONFIG: dict[str, Any] = {
    "template_dirs": ["./templates"],
    "data_dirs": ["./data"],
    "output_dir": "./output",
    "font_dir": "./fonts",
    "font_family": "DejaVu Sans",
    "recursive": True,
    "auto_open": True,
    "auto_open_limit": 5,
    "csv_engine": "auto",
    "csv_delimiter": "auto",
    "csv_encoding": "auto",
    "json_root": "auto",
    "id_field": "auto",
    "id_field_candidates": ["invoice_id", "invoice", "id", "number", "номер", "№"],
    "display_fields": ["date", "contragent", "customer", "sum", "total", "amount"],
    "filename_pattern": "{data_name}_{invoice_id}",
}


def get_project_root() -> Path:
    """Вернуть корень проекта (каталог, где лежит generate.py)."""
    return Path(__file__).resolve().parent.parent


def config_path(project_root: Path | None = None) -> Path:
    """Путь к config.json в корне проекта."""
    root = project_root or get_project_root()
    return root / "config.json"


def resolve_path(value: str | Path, project_root: Path) -> Path:
    """Разрешить путь относительно корня проекта, а не текущей рабочей директории."""
    path = Path(value)
    if path.is_absolute():
        return path
    return (project_root / path).resolve()


def load_config(project_root: Path | None = None) -> tuple[dict[str, Any], bool]:
    """Загрузить конфиг. Если файла нет — создать со значениями по умолчанию.

    Возвращает пару (конфиг, создан_ли_файл).
    """
    root = project_root or get_project_root()
    path = config_path(root)
    if not path.exists():
        cfg = deepcopy(DEFAULT_CONFIG)
        save_config(cfg, root)
        return cfg, True

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            f"Не удалось разобрать {path.name}: строка {exc.lineno}, позиция {exc.colno}."
        ) from None
    except OSError as exc:
        raise AppError(f"Не удалось прочитать {path}: {exc}") from None

    if not isinstance(data, dict):
        raise AppError(f"{path.name} должен содержать JSON-объект.")

    cfg = deepcopy(DEFAULT_CONFIG)
    cfg.update(data)
    return cfg, False


def save_config(config: dict[str, Any], project_root: Path | None = None) -> None:
    """Записать конфиг в config.json с кириллицей без экранирования."""
    root = project_root or get_project_root()
    path = config_path(root)
    try:
        path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise AppError(f"Не удалось сохранить {path}: {exc}") from None


def resolve_dir_list(values: list[str] | str, project_root: Path) -> list[Path]:
    """Разрешить список директорий из конфига."""
    if isinstance(values, str):
        values = [values]
    return [resolve_path(item, project_root) for item in values]
