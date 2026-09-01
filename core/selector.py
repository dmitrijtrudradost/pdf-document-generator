"""Консольные меню и разбор пользовательского ввода."""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import Callable

from core import AppError
from core.model import HEADER_LABELS, Document
from core.scanner import FileInfo

QUIT_WORDS = {"q", "quit", "exit"}


class UserQuit(Exception):
    """Пользователь выбрал выход из меню."""


def display_width(text: str) -> int:
    """Ширина строки в терминале с учётом широких символов."""
    width = 0
    for char in text:
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width


def clip(text: str, width: int) -> str:
    """Обрезать строку по ширине терминала, добавив многоточие."""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    if width == 1:
        return "…"
    result = ""
    for char in text:
        if display_width(result) + display_width(char) > width - 1:
            break
        result += char
    return result + "…"


def pad(text: str, width: int, align: str = "left") -> str:
    """Дополнить строку пробелами до заданной ширины отображения."""
    text = clip(text, width)
    extra = width - display_width(text)
    if extra <= 0:
        return text
    if align == "right":
        return " " * extra + text
    return text + " " * extra


def format_table(headers: list[str], rows: list[list[str]], min_widths: list[int] | None = None) -> str:
    """Таблица с шириной колонок по содержимому, шапкой и линией-разделителем."""
    if min_widths is None:
        min_widths = [len(h) for h in headers]
    widths: list[int] = []
    for index, header in enumerate(headers):
        longest = display_width(header)
        for row in rows:
            if index < len(row):
                longest = max(longest, display_width(row[index]))
        longest = max(longest, min_widths[index] if index < len(min_widths) else 0)
        widths.append(longest)

    # Не раздувать таблицу шире терминала: ужимаем самую широкую текстовую колонку.
    term_width = max(40, _terminal_width())
    overhead = 2 + 2 * (len(widths) - 1)  # ведущие пробелы и промежутки
    total = sum(widths) + overhead
    if total > term_width:
        shrink = total - term_width
        # Предпочитаем ужимать вторую колонку (имя файла / контрагент).
        target = 1 if len(widths) > 1 else 0
        widths[target] = max(8, widths[target] - shrink)

    header_line = "  " + "  ".join(pad(headers[i], widths[i]) for i in range(len(headers)))
    sep = "  " + "  ".join("─" * widths[i] for i in range(len(headers)))
    body = []
    for row in rows:
        cells = [pad(row[i] if i < len(row) else "", widths[i]) for i in range(len(headers))]
        body.append("  " + "  ".join(cells))
    return "\n".join([header_line, sep, *body])


def _terminal_width() -> int:
    try:
        return max(40, int(sys.stdout.isatty() and __import__("shutil").get_terminal_size().columns or 80))
    except OSError:
        return 80


def safe_input(prompt: str) -> str:
    """input() с корректным выходом по Ctrl+C / EOF."""
    try:
        return input(prompt)
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        raise
    except EOFError as exc:
        print("\nПрервано пользователем.")
        raise KeyboardInterrupt from exc


def format_file_table(files: list[FileInfo]) -> str:
    """Нумерованный список файлов данных или шаблонов."""
    headers = ["№", "Файл", "Тип", "Папка", "Изменён"]
    rows: list[list[str]] = []
    for index, item in enumerate(files, start=1):
        rows.append(
            [
                str(index),
                item.name,
                item.kind,
                item.parent_label,
                item.mtime.strftime("%Y-%m-%d %H:%M"),
            ]
        )
    return format_table(headers, rows, min_widths=[2, 8, 4, 6, 16])


def choose_from_files(title: str, files: list[FileInfo], empty_paths: list[str]) -> FileInfo:
    """Нумерованное меню выбора файла. Пустой ввод = вариант 1."""
    if not files:
        paths = "\n".join(f"  • {p}" for p in empty_paths) or "  • (пути не заданы)"
        raise AppError(
            "Не найдено подходящих файлов.\nПросмотренные пути:\n"
            f"{paths}\nДобавьте директорию в config.json."
        )

    print(title)
    print()
    print(format_file_table(files))
    print()
    prompt = f"Выберите файл [1-{len(files)}], q — выход: "
    while True:
        raw = safe_input(prompt).strip()
        if raw.lower() in QUIT_WORDS:
            raise UserQuit
        if raw == "":
            return files[0]
        if raw.isdigit():
            number = int(raw)
            if 1 <= number <= len(files):
                return files[number - 1]
        print(f"Некорректный ввод. Введите число от 1 до {len(files)} либо q.")


def format_document_table(documents: list[Document], start: int = 0, limit: int | None = None) -> str:
    """Список чеков: номер, invoice id и до трёх колонок из display_fields."""
    slice_ = documents[start:] if limit is None else documents[start : start + limit]
    extra_keys: list[str] = []
    if documents:
        extra_keys = list(documents[0].display.keys())
    headers = ["№", "Invoice ID"] + [HEADER_LABELS.get(k, k) for k in extra_keys]
    rows: list[list[str]] = []
    for doc in slice_:
        cells = [str(doc.row_num), doc.invoice_id]
        for key in extra_keys:
            cells.append(clip(doc.display.get(key, ""), 25))
        rows.append(cells)
    return format_table(headers, rows, min_widths=[2, 10])


def _stringify_record(value: object) -> str:
    """Плоское строковое представление записи для поиска."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_stringify_record(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_stringify_record(v) for v in value)
    return str(value)


def _get_nested(record: dict, path: str) -> object:
    current: object = record
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
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


def search_documents(documents: list[Document], query: str, field: str | None = None) -> list[Document]:
    """Регистронезависимый подстрочный поиск по всем полям или по одному полю."""
    needle = query.lower().strip()
    if not needle:
        return []
    found: list[Document] = []
    for doc in documents:
        if field:
            value = _get_nested(doc.record, field)
            haystack = _stringify_record(value).lower()
            if needle in haystack or needle in doc.invoice_id.lower():
                found.append(doc)
        else:
            haystack = " ".join(
                [
                    doc.invoice_id.lower(),
                    doc.original_id.lower(),
                    _stringify_record(doc.record).lower(),
                ]
            )
            if needle in haystack:
                found.append(doc)
    return found


@dataclass
class ParseResult:
    """Результат разбора строки выбора документов."""

    documents: list[Document] | None = None
    show_all: bool = False
    quit: bool = False
    message: str | None = None


_RANGE_TOKEN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
_INDEX_TOKEN = re.compile(r"^\d+$")
_SPEC_CHARS = re.compile(r"^[\d\s,\-]+$")


def parse_index_spec(spec: str, total: int) -> list[int] | None:
    """Разобрать all, 3, 2-7, 1,4,9, 2-4,8,11-12 в 1-based индексы.

    Возвращает None, если строка не похожа на спецификацию номеров.
    """
    text = spec.strip()
    if text.lower() in {"all", "*"}:
        return list(range(1, total + 1))
    if not _SPEC_CHARS.match(text):
        return None
    result: list[int] = []
    for part in text.split(","):
        token = part.strip()
        if not token:
            continue
        range_match = _RANGE_TOKEN.match(token)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if start > end:
                start, end = end, start
            result.extend(range(start, end + 1))
            continue
        if _INDEX_TOKEN.match(token):
            result.append(int(token))
            continue
        return None
    unique: list[int] = []
    seen: set[int] = set()
    for number in result:
        if number < 1 or number > total:
            continue
        if number not in seen:
            seen.add(number)
            unique.append(number)
    return unique


def parse_document_choice(text: str, documents: list[Document]) -> ParseResult:
    """Разобрать ввод: номер, id, поиск, диапазон, all, r, q."""
    raw = text.strip()
    if raw.lower() in QUIT_WORDS:
        return ParseResult(quit=True)
    if raw.lower() == "r":
        return ParseResult(show_all=True)
    if not raw:
        return ParseResult(message="Введите номер, invoice id, поиск /текст или q.")

    if raw.startswith("/"):
        body = raw[1:]
        field: str | None = None
        query = body
        if "=" in body:
            field, query = body.split("=", 1)
            field = field.strip()
            query = query.strip()
        found = search_documents(documents, query, field)
        if not found:
            return ParseResult(message="Ничего не найдено. Попробуйте другой запрос.")
        return ParseResult(documents=found)

    spec = parse_index_spec(raw, len(documents))
    if spec is not None:
        if spec:
            by_num = {doc.row_num: doc for doc in documents}
            chosen = [by_num[n] for n in spec if n in by_num]
            return ParseResult(documents=chosen)
        # Одно число вне диапазона списка — это может быть фрагмент invoice id (например 1025).
        if not raw.isdigit():
            return ParseResult(
                message=f"Номера вне диапазона 1–{len(documents)}."
            )

    lowered = raw.lower()
    exact = [doc for doc in documents if doc.invoice_id.lower() == lowered]
    if not exact:
        exact = [doc for doc in documents if doc.original_id.lower() == lowered]
    if len(exact) == 1:
        return ParseResult(documents=exact)
    if len(exact) > 1:
        ids = ", ".join(d.invoice_id for d in exact)
        return ParseResult(message=f"Найдено несколько точных совпадений: {ids}. Уточните выбор.")

    partial = [
        doc
        for doc in documents
        if lowered in doc.invoice_id.lower() or lowered in doc.original_id.lower()
    ]
    if len(partial) == 1:
        return ParseResult(documents=partial)
    if len(partial) > 1:
        preview = format_document_table(partial)
        return ParseResult(
            message="Найдено несколько документов, уточните выбор:\n" + preview
        )
    return ParseResult(message=f"Документ {raw!r} не найден.")


def paginate_documents(documents: list[Document], page_size: int = 20) -> None:
    """Показать полный список по 20 строк с паузой."""
    total = len(documents)
    if total == 0:
        print("Список пуст.")
        return
    offset = 0
    while offset < total:
        print(format_document_table(documents, start=offset, limit=page_size))
        offset += page_size
        if offset < total:
            answer = safe_input("Enter — следующие 20, q — к запросу: ").strip().lower()
            if answer in QUIT_WORDS:
                return


def choose_documents(
    documents: list[Document],
    data_label: str,
    id_field: str,
) -> list[Document]:
    """Интерактивный выбор одного или нескольких документов."""
    print(f"Файл: {data_label}")
    print(f"Поле идентификатора: {id_field}")
    print()
    print("Доступные чеки:")
    print()
    preview_limit = 20
    print(format_document_table(documents, start=0, limit=preview_limit))
    if len(documents) > preview_limit:
        print(f"  … показаны первые {preview_limit} из {len(documents)}. r — полный список.")
    print()
    print(
        "Выберите чек: номер из списка, invoice id, /текст — поиск,"
    )
    print("all — все, 2-7 — диапазон, r — показать все, q — выход")

    while True:
        raw = safe_input("> ")
        result = parse_document_choice(raw, documents)
        if result.quit:
            raise UserQuit
        if result.show_all:
            paginate_documents(documents)
            continue
        if result.message:
            print(result.message)
            continue
        if result.documents:
            return result.documents


def confirm_multiple(count: int, assume_yes: bool) -> bool:
    """Подтверждение при выборе более одного документа."""
    if assume_yes or count <= 1:
        return True
    answer = safe_input(f"Будет создано {count} PDF [Y/n]: ").strip().lower()
    if answer in {"", "y", "yes", "д", "да"}:
        return True
    return False


def choose_id_field_interactive(
    fields: list[str],
    on_refuse: Callable[[], str],
) -> str:
    """Предложить выбрать поле-идентификатор номером."""
    print("Автоматически определить поле invoice id не удалось.")
    print("Доступные поля:")
    for index, name in enumerate(fields, start=1):
        print(f"  {index}. {name}")
    print("Пустой ввод — использовать порядковый номер записи.")
    while True:
        raw = safe_input(f"Выберите поле [1-{len(fields)}] или Enter: ").strip()
        if raw.lower() in QUIT_WORDS:
            raise UserQuit
        if raw == "":
            return on_refuse()
        if raw.isdigit() and 1 <= int(raw) <= len(fields):
            return fields[int(raw) - 1]
        print("Некорректный ввод, повторите.")
