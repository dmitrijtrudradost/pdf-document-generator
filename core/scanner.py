"""Поиск файлов данных (CSV/JSON) и HTML-шаблонов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DATA_EXTENSIONS = {".csv": "CSV", ".json": "JSON"}
TEMPLATE_EXTENSIONS = {".html": "HTML", ".htm": "HTML"}


@dataclass
class FileInfo:
    """Описание найденного файла для меню и CLI."""

    path: Path
    kind: str
    size: int
    mtime: datetime

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def parent_label(self) -> str:
        """Родительская папка в сокращённом виде."""
        return shorten_path(self.path.parent)


def shorten_path(path: Path, max_len: int = 16) -> str:
    """Сократить путь для колонки «Папка»: относительно проекта, иначе абсолютный."""
    from core.config import get_project_root

    try:
        relative = path.resolve().relative_to(get_project_root())
        text = relative.as_posix() if str(relative) != "." else path.name
    except ValueError:
        text = str(path)
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return "…"
    return text[: max_len - 1] + "…"


def _iter_files(directory: Path, recursive: bool) -> list[Path]:
    """Вернуть файлы в директории с учётом флага recursive."""
    if recursive:
        return [p for p in directory.rglob("*") if p.is_file()]
    return [p for p in directory.iterdir() if p.is_file()]


def scan_directory(
    directory: Path,
    extensions: dict[str, str],
    recursive: bool,
) -> tuple[list[FileInfo], str | None]:
    """Просканировать одну директорию. Несуществующая — предупреждение, не падение."""
    if not directory.exists():
        return [], f"Директория не существует: {directory}"
    if not directory.is_dir():
        return [], f"Путь не является директорией: {directory}"

    found: list[FileInfo] = []
    try:
        candidates = _iter_files(directory, recursive)
    except OSError as exc:
        return [], f"Не удалось прочитать директорию {directory}: {exc}"

    for path in candidates:
        kind = extensions.get(path.suffix.lower())
        if kind is None:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        found.append(
            FileInfo(
                path=path.resolve(),
                kind=kind,
                size=stat.st_size,
                mtime=datetime.fromtimestamp(stat.st_mtime),
            )
        )
    return found, None


def scan_many(
    directories: list[Path],
    extensions: dict[str, str],
    recursive: bool,
) -> tuple[list[FileInfo], list[str]]:
    """Просканировать несколько директорий, собрать предупреждения."""
    all_files: list[FileInfo] = []
    warnings: list[str] = []
    seen: set[Path] = set()
    for directory in directories:
        files, warning = scan_directory(directory, extensions, recursive)
        if warning:
            warnings.append(warning)
        for item in files:
            if item.path in seen:
                continue
            seen.add(item.path)
            all_files.append(item)
    all_files.sort(key=lambda f: f.mtime, reverse=True)
    return all_files, warnings


def scan_data_files(
    data_dirs: list[Path],
    recursive: bool,
) -> tuple[list[FileInfo], list[str]]:
    """Найти CSV и JSON в каталогах данных."""
    return scan_many(data_dirs, DATA_EXTENSIONS, recursive)


def scan_templates(
    template_dirs: list[Path],
    recursive: bool,
) -> tuple[list[FileInfo], list[str]]:
    """Найти HTML-шаблоны."""
    return scan_many(template_dirs, TEMPLATE_EXTENSIONS, recursive)


def find_by_name_or_path(
    spec: str,
    scanned: list[FileInfo],
    project_root: Path,
) -> FileInfo | None:
    """Найти файл по полному пути или только по имени среди просканированных."""
    raw = Path(spec)
    candidates = [raw]
    if not raw.is_absolute():
        candidates.append(project_root / raw)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file():
            kind = DATA_EXTENSIONS.get(resolved.suffix.lower()) or TEMPLATE_EXTENSIONS.get(
                resolved.suffix.lower()
            ) or resolved.suffix.upper().lstrip(".")
            try:
                stat = resolved.stat()
            except OSError:
                continue
            return FileInfo(
                path=resolved,
                kind=kind,
                size=stat.st_size,
                mtime=datetime.fromtimestamp(stat.st_mtime),
            )

    needle = raw.name.lower()
    matches = [item for item in scanned if item.path.name.lower() == needle]
    if matches:
        return matches[0]
    return None
