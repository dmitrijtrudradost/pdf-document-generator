"""Подстановка данных в HTML-шаблон: плейсхолдеры, вложенность, циклы, фильтры."""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

from core.model import format_date, format_money

PLACEHOLDER_RE = re.compile(
    r"\{\{\s*([A-Za-z0-9_\-\.]+)(\s*\|\s*[a-z]+)?\s*\}\}"
)
LOOP_RE = re.compile(
    r"\{\{#([A-Za-z0-9_]+)\}\}(.*?)\{\{/\1\}\}",
    re.DOTALL,
)
LOOP_OPEN_RE = re.compile(r"\{\{#([A-Za-z0-9_]+)\}\}")


def apply_filter(value: str, name: str | None) -> str:
    """Применить фильтр форматирования к строковому значению."""
    if not name:
        return value
    if name == "money":
        return format_money(value)
    if name == "date":
        return format_date(value)
    if name == "upper":
        return value.upper()
    if name == "lower":
        return value.lower()
    if name == "strip":
        return value.strip()
    return value


def _lookup(source: dict[str, Any], path: str) -> Any:
    """Достать значение по точечному пути. Отсутствующий узел → None."""
    current: Any = source
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        if part in current:
            current = current[part]
            continue
        found = None
        target = part.lower()
        for key, val in current.items():
            if str(key).lower() == target:
                found = val
                break
        if found is None:
            return None
        current = found
    return current


def _stringify(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value)


def _replace_placeholders(text: str, primary: dict[str, Any], fallback: dict[str, Any] | None = None) -> str:
    """Заменить {{ field }} и {{ field|filter }}. Сначала primary, затем fallback."""

    def repl(match: re.Match[str]) -> str:
        field = match.group(1)
        raw_filter = match.group(2)
        filter_name = raw_filter.split("|", 1)[-1].strip() if raw_filter else None
        value = _lookup(primary, field)
        if value is None and fallback is not None:
            value = _lookup(fallback, field)
        rendered = apply_filter(_stringify(value), filter_name)
        return html.escape(rendered, quote=True)

    return PLACEHOLDER_RE.sub(repl, text)


def _expand_loops(template: str, record: dict[str, Any]) -> tuple[str, list[str]]:
    """Раскрыть один уровень циклов {{#items}}…{{/items}}. Вернуть HTML и предупреждения."""
    warnings: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        inner = match.group(2)
        value = _lookup(record, name)
        if not isinstance(value, list):
            warnings.append(
                f"Цикл {{{{#{name}}}}} : поле {name!r} отсутствует или не является списком — блок пуст."
            )
            return ""
        chunks: list[str] = []
        for index, item in enumerate(value, start=1):
            if not isinstance(item, dict):
                continue
            ctx = {**item, "__index__": index}
            chunks.append(_replace_placeholders(inner, ctx, fallback=record))
        return "".join(chunks)

    return LOOP_RE.sub(repl, template), warnings


def build_service_context(
    *,
    invoice_id: str,
    data_name: str,
    row_num: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Служебные плейсхолдеры документа."""
    moment = now or datetime.now()
    return {
        "__invoice_id__": invoice_id,
        "__date__": moment.strftime("%d.%m.%Y"),
        "__datetime__": moment.strftime("%d.%m.%Y %H:%M"),
        "__data_name__": data_name,
        "__row_num__": row_num,
    }


def render_template(
    template: str,
    record: dict[str, Any],
    service: dict[str, Any],
) -> tuple[str, list[str]]:
    """Подставить данные в шаблон. Циклы, затем плейсхолдеры, экранирование значений."""
    context = {**record, **service}
    expanded, warnings = _expand_loops(template, context)
    html_out = _replace_placeholders(expanded, context)
    return html_out, warnings


def extract_placeholders(template: str) -> tuple[list[str], list[str], set[str]]:
    """Плейсхолдеры шаблона, имена циклов и поля, встречающиеся только внутри циклов."""
    loops = LOOP_OPEN_RE.findall(template)
    without_loops = LOOP_RE.sub("", template)
    outer = [match.group(1) for match in PLACEHOLDER_RE.finditer(without_loops)]
    inner: list[str] = []
    for match in LOOP_RE.finditer(template):
        inner.extend(m.group(1) for m in PLACEHOLDER_RE.finditer(match.group(2)))
    ordered: list[str] = []
    seen: set[str] = set()
    for name in outer + inner:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    loop_names: list[str] = []
    loop_seen: set[str] = set()
    for name in loops:
        if name not in loop_seen:
            loop_seen.add(name)
            loop_names.append(name)
    return ordered, loop_names, set(inner)


def flatten_available(record: dict[str, Any], prefix: str = "") -> list[str]:
    """Поля записи, вложенные в виде customer.name."""
    names: list[str] = []
    for key, value in record.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        names.append(path)
        if isinstance(value, dict):
            names.extend(flatten_available(value, path))
    return names


def reconcile_template(
    template: str,
    record: dict[str, Any],
    service: dict[str, Any],
) -> list[str]:
    """Сверка плейсхолдеров шаблона с полями записи. Возвращает строки отчёта."""
    placeholders, loops, inner_fields = extract_placeholders(template)
    context = {**record, **service}
    available = flatten_available(context)

    lines: list[str] = []
    ph_list = ", ".join(placeholders) if placeholders else "(нет)"
    loop_list = ", ".join(f"{{{{#{name}}}}}" for name in loops) if loops else "(нет)"
    lines.append(f"Плейсхолдеры шаблона: {ph_list}")
    lines.append(f"Циклы: {loop_list}")
    lines.append("Поля записи: " + (", ".join(available) if available else "(нет)"))

    missing = [
        name
        for name in placeholders
        if name not in inner_fields and _lookup(context, name) is None
    ]
    if missing:
        lines.append("[!] Нет данных для: " + ", ".join(missing) + " — будет пустая строка.")

    used = set(placeholders) | set(loops) | inner_fields
    unused: list[str] = []
    for name in flatten_available(record):
        if name.split(".")[0] in loops:
            continue
        related = any(
            name == item or name.startswith(item + ".") or item.startswith(name + ".")
            for item in used
        )
        if not related:
            unused.append(name)
    if unused:
        lines.append("Поля, не используемые в шаблоне: " + ", ".join(unused))

    for name in loops:
        value = _lookup(record, name)
        if not isinstance(value, list):
            lines.append(
                f"[!] Цикл {{{{#{name}}}}} : поле отсутствует или не список — блок будет пустым."
            )

    return lines
