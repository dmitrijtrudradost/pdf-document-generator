"""HTML → PDF через WeasyPrint, шрифты и CSS страницы A4."""

from __future__ import annotations

import contextlib
import io
import os
import re
import sys
from pathlib import Path

from core import AppError

FONT_FILES = {
    "dejavu sans": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    "roboto": ("Roboto-Regular.ttf", "Roboto-Bold.ttf"),
    "liberation sans": ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
}

UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|]+')


def sanitize_filename(name: str, max_len: int = 100) -> str:
    """Удалить запрещённые символы, схлопнуть пробелы в _, сохранить кириллицу."""
    cleaned = UNSAFE_FILENAME.sub("", name)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
    if not cleaned:
        cleaned = "document"
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("._ ")
    return cleaned


def unique_output_path(path: Path) -> Path:
    """Если файл существует — добавить суффикс _2, _3, не перезаписывать."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def make_pdf_filename(
    pattern: str,
    *,
    data_name: str,
    invoice_id: str,
    row_num: int,
    date: str,
) -> str:
    """Собрать имя PDF по filename_pattern."""
    try:
        raw = pattern.format(
            data_name=data_name,
            invoice_id=invoice_id,
            row_num=row_num,
            date=date,
        )
    except (KeyError, ValueError):
        raw = f"{data_name}_{invoice_id}"
    if not raw.lower().endswith(".pdf"):
        raw += ".pdf"
    stem = Path(raw).stem
    return sanitize_filename(stem) + ".pdf"


def find_font_files(font_dir: Path, font_family: str) -> tuple[Path | None, Path | None, list[str]]:
    """Найти regular/bold файлы шрифта. Предупреждения, если файлов нет."""
    warnings: list[str] = []
    key = font_family.strip().lower()
    names = FONT_FILES.get(key, (f"{font_family.replace(' ', '')}.ttf", f"{font_family.replace(' ', '')}-Bold.ttf"))
    regular = font_dir / names[0]
    bold = font_dir / names[1]
    regular_ok = regular if regular.is_file() else None
    bold_ok = bold if bold.is_file() else None
    if regular_ok is None:
        expected = " и ".join(str(font_dir / n) for n in names)
        warnings.append(
            f"Файлы шрифта «{font_family}» не найдены. Положите {names[0]} и {names[1]} "
            f"в {font_dir} (ожидались: {expected}). Будет использован стандартный sans-serif."
        )
    elif bold_ok is None:
        warnings.append(
            f"Не найден жирный файл шрифта {names[1]} в {font_dir}. Жирное начертание может совпасть с обычным."
        )
    return regular_ok, bold_ok, warnings


def build_page_css(font_dir: Path, font_family: str) -> tuple[str, list[str]]:
    """CSS страницы A4, таблиц и @font-face."""
    regular, bold, warnings = find_font_files(font_dir, font_family)
    faces: list[str] = []
    if regular is not None:
        faces.append(
            f"""@font-face {{
  font-family: '{font_family}';
  src: url('{regular.resolve().as_uri()}');
  font-weight: 400;
  font-style: normal;
}}"""
        )
    if bold is not None:
        faces.append(
            f"""@font-face {{
  font-family: '{font_family}';
  src: url('{bold.resolve().as_uri()}');
  font-weight: 700;
  font-style: normal;
}}"""
        )
    family = f"'{font_family}', sans-serif" if regular is not None else "sans-serif"
    css = f"""
{" ".join(faces)}
@page {{
  size: A4;
  margin: 15mm;
}}
html, body {{
  font-family: {family};
  font-size: 11pt;
  color: #111;
  margin: 0;
  padding: 0;
}}
table {{
  border-collapse: collapse;
  width: 100% !important;
  max-width: 100% !important;
  table-layout: fixed;
  margin: 12px 0 16px;
  box-sizing: border-box;
}}
table, th, td {{
  border: 1px solid #333;
}}
th, td {{
  box-sizing: border-box;
  padding: 6px 8px;
  word-wrap: break-word;
  overflow-wrap: break-word;
  word-break: break-word;
  hyphens: auto;
  max-width: 0;
}}
th {{
  background: #e8e8e8;
  font-weight: 700;
  text-align: center;
}}
td.num, th.num {{
  text-align: right;
  max-width: none;
  overflow-wrap: normal;
  word-break: normal;
}}
thead {{
  display: table-header-group;
}}
tr {{
  page-break-inside: avoid;
}}
"""
    return css, warnings


def _prepend_gtk_bin() -> None:
    """На Windows добавить каталог GTK в PATH, если runtime уже установлен."""
    if sys.platform != "win32":
        return
    candidates = [
        os.environ.get("GTK3_RUNTIME_BIN", ""),
        r"C:\Program Files\GTK3-Runtime Win64\bin",
        r"C:\Program Files (x86)\GTK3-Runtime Win64\bin",
        r"C:\GTK3-Runtime Win64\bin",
    ]
    extra: list[str] = []
    for raw in candidates:
        if not raw:
            continue
        folder = Path(raw)
        if folder.is_dir():
            extra.append(str(folder.resolve()))
    if extra:
        os.environ["PATH"] = os.pathsep.join(extra) + os.pathsep + os.environ.get("PATH", "")


_HTML = None
_CSS = None
_import_error: AppError | None = None


def _import_weasyprint():
    """Импортировать WeasyPrint с понятной ошибкой про GTK на Windows."""
    global _HTML, _CSS, _import_error
    if _import_error is not None:
        raise _import_error
    if _HTML is not None:
        return _HTML, _CSS

    _prepend_gtk_bin()
    sink = io.StringIO()
    try:
        with contextlib.redirect_stderr(sink), contextlib.redirect_stdout(sink):
            from weasyprint import CSS, HTML  # type: ignore
    except ImportError:
        _import_error = AppError(
            "WeasyPrint не установлен. Выполните: pip install weasyprint\n"
            "На Windows дополнительно нужен GTK Runtime:\n"
            "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases"
        )
        raise _import_error from None
    except OSError as exc:
        _import_error = AppError(
            "WeasyPrint не смог загрузиться (часто на Windows не установлен GTK).\n"
            "Установите GTK Runtime и перезапустите терминал:\n"
            "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases\n"
            f"Подробности: {exc}"
        )
        raise _import_error from None
    _HTML, _CSS = HTML, CSS
    return HTML, CSS


def ensure_weasyprint() -> None:
    """Проверить доступность WeasyPrint и GTK до начала генерации."""
    _import_weasyprint()


def html_to_pdf(
    html_text: str,
    output_path: Path,
    *,
    base_url: Path,
    font_dir: Path,
    font_family: str,
) -> list[str]:
    """Сформировать PDF. Промежуточный HTML на диск не пишется."""
    HTML, CSS = _import_weasyprint()
    css_text, warnings = build_page_css(font_dir, font_family)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AppError(f"Нет прав на создание папки {output_path.parent}: {exc}") from None

    try:
        HTML(string=html_text, base_url=str(base_url.resolve())).write_pdf(
            target=str(output_path),
            stylesheets=[CSS(string=css_text)],
        )
    except PermissionError as exc:
        raise AppError(f"Нет прав на запись в {output_path.parent}: {exc}") from None
    except OSError as exc:
        message = str(exc)
        if "cannot load" in message.lower() or "gobject" in message.lower() or "libgobject" in message.lower():
            raise AppError(
                "WeasyPrint не смог отрисовать PDF — не найден GTK.\n"
                "На Windows установите GTK Runtime и перезапустите терминал.\n"
                "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases"
            ) from None
        raise AppError(f"Ошибка записи PDF {output_path.name}: {exc}") from None
    except Exception as exc:
        raise AppError(f"Ошибка рендера PDF {output_path.name}: {exc}") from None
    return warnings
