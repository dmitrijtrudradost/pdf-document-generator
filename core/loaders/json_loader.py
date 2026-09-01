"""Загрузка JSON: четыре поддерживаемые структуры корневого объекта."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core import AppError


def _read_json_text(path: Path) -> str:
    """Прочитать JSON: utf-8, при ошибке — utf-8-sig."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AppError(
                f"Не удалось прочитать {path.name} в кодировке utf-8: {exc}."
            ) from None
    except OSError as exc:
        raise AppError(f"Не удалось прочитать {path.name}: {exc}") from None


def _parse_json(path: Path) -> Any:
    """Разобрать JSON с понятным сообщением об ошибке синтаксиса."""
    text = _read_json_text(path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(
            f"Ошибка разбора JSON в файле {path.name}: "
            f"строка {exc.lineno}, позиция {exc.colno}."
        ) from None


def _as_object_list(value: Any) -> tuple[list[dict[str, Any]], int]:
    """Оставить только словари, вернуть (записи, сколько пропущено)."""
    if not isinstance(value, list):
        return [], 0
    records: list[dict[str, Any]] = []
    skipped = 0
    for item in value:
        if isinstance(item, dict):
            records.append(item)
        else:
            skipped += 1
    return records, skipped


def _from_id_map(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Словарь id → объект: ключ становится invoice_id, если поля внутри нет."""
    records: list[dict[str, Any]] = []
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        record = dict(value)
        if "invoice_id" not in record or record["invoice_id"] in (None, ""):
            record["invoice_id"] = str(key)
        records.append(record)
    return records


def _first_object_array_key(data: dict[str, Any]) -> str | None:
    """Найти первый ключ, значение которого — список объектов."""
    for key, value in data.items():
        if not isinstance(value, list) or not value:
            continue
        if any(isinstance(item, dict) for item in value):
            return str(key)
    return None


def _all_values_are_objects(data: dict[str, Any]) -> bool:
    """Проверить, что все значения словаря — объекты (структура id → запись)."""
    if not data:
        return False
    return all(isinstance(value, dict) for value in data.values())


_RECORD_HINTS = {
    "invoice_id",
    "invoice",
    "id",
    "number",
    "номер",
    "date",
    "contragent",
    "customer",
    "total",
    "sum",
    "amount",
}


def _norm_key(name: str) -> str:
    """Нормализация имени ключа: без регистра, пробелов и подчёркиваний."""
    return "".join(ch for ch in name.lower() if ch not in " _")


def _looks_like_single_record(data: dict[str, Any]) -> bool:
    """Отличить один документ со вложенным items[] от обёртки {invoices: [...]}."""
    keys = {_norm_key(str(k)) for k in data}
    hints = {_norm_key(h) for h in _RECORD_HINTS}
    if not (keys & hints):
        return False
    # У обёртки все «полезные» данные — в массиве, у записи есть скаляры/объекты рядом.
    return not _all_values_are_objects(data)


def load_json(
    path: Path,
    json_root: str = "auto",
) -> tuple[list[dict[str, Any]], int]:
    """Загрузить JSON и вернуть (список записей, число пропущенных не-объектов).

    Вложенность не разворачивается — она нужна шаблонам.
    """
    data = _parse_json(path)
    skipped = 0
    root = (json_root or "auto").strip()

    if isinstance(data, list):
        records, skipped = _as_object_list(data)
        return records, skipped

    if not isinstance(data, dict):
        raise AppError(
            f"Неопознанная структура JSON в {path.name}: корневой элемент имеет тип "
            f"{type(data).__name__}. Укажите ключ массива через --json-root."
        )

    if root.lower() != "auto":
        if root not in data:
            available = ", ".join(data.keys()) or "(пусто)"
            raise AppError(
                f"В {path.name} нет ключа {root!r}. Доступные ключи: {available}."
            )
        records, skipped = _as_object_list(data[root])
        if not records and not isinstance(data[root], list):
            raise AppError(
                f"Ключ {root!r} в {path.name} не содержит массив объектов. "
                f"Тип значения: {type(data[root]).__name__}."
            )
        return records, skipped

    # Один документ с полем items[] не должен восприниматься как обёртка массива.
    if _looks_like_single_record(data):
        return [data], 0

    array_key = _first_object_array_key(data)
    if array_key is not None:
        records, skipped = _as_object_list(data[array_key])
        return records, skipped

    if _all_values_are_objects(data):
        return _from_id_map(data), 0

    return [data], 0
