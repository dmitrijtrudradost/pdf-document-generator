"""Определение invoice id, уникальность и подготовка списка документов."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core import AppError

HEADER_LABELS = {
    "date": "Дата",
    "contragent": "Контрагент",
    "customer": "Контрагент",
    "sum": "Сумма",
    "total": "Сумма",
    "amount": "Сумма",
}

MONEY_FIELDS = {"sum", "total", "amount"}
DATE_FIELDS = {"date"}


def normalize_field_name(name: str) -> str:
    """Сравнение имён: без регистра, пробелов и подчёркиваний."""
    return re.sub(r"[\s_]+", "", name).lower()


def find_key(record: dict[str, Any], name: str) -> str | None:
    """Найти фактический ключ в записи по нормализованному имени."""
    target = normalize_field_name(name)
    for key in record:
        if normalize_field_name(str(key)) == target:
            return str(key)
    return None


def get_field(record: dict[str, Any], name: str) -> Any:
    """Достать значение поля с регистронезависимым поиском ключа."""
    key = find_key(record, name)
    if key is None:
        return None
    return record.get(key)


def flatten_fields(record: dict[str, Any], prefix: str = "") -> list[str]:
    """Список доступных полей, вложенные — в виде customer.name."""
    names: list[str] = []
    for key, value in record.items():
        path = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        names.append(path)
        if isinstance(value, dict):
            names.extend(flatten_fields(value, path))
    return names


def _value_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (dict, list)):
        return bool(value)
    return str(value).strip() != ""


def detect_id_field(
    records: list[dict[str, Any]],
    candidates: list[str],
) -> str | None:
    """Первое поле из кандидатов, которое есть во всех записях и непустое."""
    if not records:
        return None
    for candidate in candidates:
        actual: str | None = None
        ok = True
        for record in records:
            key = find_key(record, candidate)
            if key is None or not _value_nonempty(record.get(key)):
                ok = False
                break
            actual = key
        if ok and actual:
            return actual
    return None


def unique_ids(values: list[str]) -> tuple[list[str], bool]:
    """Сделать идентификаторы уникальными суффиксами #2, #3. Вернуть (id, были_дубли)."""
    counts: dict[str, int] = {}
    seen: dict[str, int] = {}
    result: list[str] = []
    had_dupes = False
    for value in values:
        seen[value] = seen.get(value, 0) + 1
    for value in values:
        if seen[value] == 1:
            result.append(value)
            continue
        had_dupes = True
        counts[value] = counts.get(value, 0) + 1
        n = counts[value]
        result.append(value if n == 1 else f"{value}#{n}")
    return result, had_dupes


def format_money(value: Any) -> str:
    """120000 → 120 000,00 с неразрывным пробелом. Нечисловое — без изменений."""
    if value is None:
        return ""
    text = str(value).strip()
    if text == "":
        return ""
    normalized = text.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    try:
        number = float(normalized)
    except ValueError:
        return text
    formatted = f"{number:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", "\u00a0")
    return formatted


def format_date(value: Any) -> str:
    """ISO 2026-08-01 → 01.08.2026. Уже отформатированное значение не трогать."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$", text)
    if match:
        year, month, day = match.groups()
        return f"{day}.{month}.{year}"
    return text


def _display_value(field_name: str, value: Any) -> str:
    """Подготовить значение колонки списка документов."""
    if isinstance(value, dict):
        for nested in ("name", "title", "label"):
            if nested in value and _value_nonempty(value[nested]):
                return str(value[nested]).strip()
        return ""
    if isinstance(value, list):
        return ""
    text = "" if value is None else str(value).strip()
    norm = normalize_field_name(field_name)
    if norm in MONEY_FIELDS:
        return format_money(text)
    if norm in DATE_FIELDS:
        return format_date(text)
    return text


def pick_display_fields(
    records: list[dict[str, Any]],
    display_fields: list[str],
    limit: int = 3,
) -> list[str]:
    """Первые найденные поля из display_fields, максимум limit колонок."""
    if not records:
        return []
    chosen: list[str] = []
    for name in display_fields:
        if any(find_key(record, name) for record in records):
            chosen.append(name)
        if len(chosen) >= limit:
            break
    return chosen


@dataclass
class Document:
    """Документ (чек/счёт) после подготовки списка."""

    row_num: int
    invoice_id: str
    original_id: str
    record: dict[str, Any]
    display: dict[str, str] = field(default_factory=dict)


def build_documents(
    records: list[dict[str, Any]],
    id_field: str,
    display_fields: list[str],
) -> tuple[list[Document], bool]:
    """Собрать список документов и пометить дубли идентификаторов."""
    raw_ids: list[str] = []
    for index, record in enumerate(records, start=1):
        value = get_field(record, id_field)
        if value is None or str(value).strip() == "":
            raw_ids.append(str(index))
        else:
            raw_ids.append(str(value).strip())

    unique, had_dupes = unique_ids(raw_ids)
    columns = pick_display_fields(records, display_fields)
    documents: list[Document] = []
    for index, record in enumerate(records):
        display: dict[str, str] = {}
        for col in columns:
            display[col] = _display_value(col, get_field(record, col))
        documents.append(
            Document(
                row_num=index + 1,
                invoice_id=unique[index],
                original_id=raw_ids[index],
                record=record,
                display=display,
            )
        )
    return documents, had_dupes


def available_field_names(records: list[dict[str, Any]]) -> list[str]:
    """Уникальные имена полей по всем записям (верхний уровень)."""
    names: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                seen.add(key)
                names.append(str(key))
    return names


def resolve_id_field_explicit(
    records: list[dict[str, Any]],
    name: str,
) -> str:
    """Найти реальное имя поля по --id-field."""
    for record in records:
        key = find_key(record, name)
        if key:
            return key
    available = ", ".join(available_field_names(records)) or "(нет полей)"
    raise AppError(
        f"Поле идентификатора {name!r} не найдено. Доступные поля: {available}."
    )
