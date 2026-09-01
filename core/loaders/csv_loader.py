"""Загрузка CSV: pandas (если есть) или стандартный модуль csv."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from core import AppError

ENCODINGS_AUTO = ("utf-8-sig", "utf-8", "cp1251")


def detect_encoding(path: Path, configured: str) -> str:
    """Определить кодировку файла. При auto пробуются utf-8-sig, utf-8, cp1251."""
    if configured and configured.lower() != "auto":
        return configured

    last_error: UnicodeDecodeError | None = None
    for encoding in ENCODINGS_AUTO:
        try:
            path.read_text(encoding=encoding)
            return encoding
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except OSError as exc:
            raise AppError(f"Не удалось прочитать файл {path.name}: {exc}") from None

    hint = f" ({last_error})" if last_error else ""
    raise AppError(
        f"Не удалось определить кодировку файла {path.name}.{hint} "
        "Укажите csv_encoding в config.json (utf-8, utf-8-sig или cp1251)."
    )


def detect_delimiter(text: str, configured: str) -> str:
    """Определить разделитель: Sniffer, затем «;», затем «,»."""
    if configured and configured.lower() != "auto":
        return configured

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
        if dialect.delimiter:
            return dialect.delimiter
    except csv.Error:
        pass

    if sample.count(";") >= sample.count(","):
        return ";"
    return ","


def _clean_records(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Обрезать пробелы, превратить None в пустую строку, пропустить пустые строки."""
    result: list[dict[str, str]] = []
    for row in rows:
        cleaned: dict[str, str] = {}
        for key, value in row.items():
            name = (key or "").strip()
            if not name:
                continue
            text = "" if value is None else str(value).strip()
            if text.lower() == "nan":
                text = ""
            cleaned[name] = text
        if cleaned and any(v != "" for v in cleaned.values()):
            result.append(cleaned)
    return result


def _load_stdlib(path: Path, encoding: str, delimiter: str) -> list[dict[str, str]]:
    """Загрузить CSV стандартным модулем csv."""
    try:
        with path.open(encoding=encoding, newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames:
                raise AppError(
                    f"CSV-файл {path.name} пустой или не содержит заголовка."
                )
            raw_rows = [dict(row) for row in reader]
    except AppError:
        raise
    except OSError as exc:
        raise AppError(f"Не удалось прочитать {path.name}: {exc}") from None

    records = _clean_records(raw_rows)
    if not records:
        raise AppError(
            f"CSV-файл {path.name} содержит только заголовок или пустые строки."
        )
    return records


def _load_pandas(path: Path, encoding: str, delimiter: str) -> list[dict[str, str]]:
    """Загрузить CSV через pandas. Импорт внутри функции, как требует ТЗ."""
    try:
        import pandas as pd
    except ImportError:
        raise AppError(
            "csv_engine установлен в «pandas», но библиотека не установлена.\n"
            "Установите: pip install pandas\n"
            "Либо в config.json задайте \"csv_engine\": \"stdlib\"."
        ) from None

    try:
        frame = pd.read_csv(
            path,
            encoding=encoding,
            sep=delimiter,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
        )
    except Exception as exc:  # pandas даёт разные типы ошибок
        raise AppError(f"Не удалось прочитать CSV {path.name} через pandas: {exc}") from None

    if frame.empty or len(frame.columns) == 0:
        raise AppError(
            f"CSV-файл {path.name} пустой или содержит только заголовок."
        )
    records = _clean_records(frame.to_dict(orient="records"))
    if not records:
        raise AppError(
            f"CSV-файл {path.name} содержит только заголовок или пустые строки."
        )
    return records


def _resolve_engine(configured: str) -> str:
    """Выбрать движок: auto → pandas при наличии, иначе stdlib."""
    engine = (configured or "auto").lower()
    if engine not in {"auto", "pandas", "stdlib"}:
        raise AppError(
            f"Неизвестное значение csv_engine: {configured!r}. "
            "Допустимо: auto, pandas, stdlib."
        )
    if engine == "pandas":
        return "pandas"
    if engine == "stdlib":
        return "stdlib"
    try:
        import pandas as pd  # noqa: F401

        return "pandas"
    except ImportError:
        return "stdlib"


def load_csv(path: Path, config: dict[str, Any]) -> tuple[list[dict[str, str]], str, str, str]:
    """Загрузить CSV и вернуть записи вместе с выбранными кодировкой, разделителем и движком."""
    encoding = detect_encoding(path, str(config.get("csv_encoding", "auto")))
    text = path.read_text(encoding=encoding)
    delimiter = detect_delimiter(text, str(config.get("csv_delimiter", "auto")))
    engine = _resolve_engine(str(config.get("csv_engine", "auto")))

    if engine == "pandas":
        records = _load_pandas(path, encoding, delimiter)
    else:
        records = _load_stdlib(path, encoding, delimiter)
    return records, encoding, delimiter, engine
