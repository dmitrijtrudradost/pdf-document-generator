"""Генератор PDF-документов из CSV/JSON по HTML-шаблону."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from core import AppError
from core.config import (
    get_project_root,
    load_config,
    resolve_dir_list,
    resolve_path,
)
from core.loaders import load_data
from core.model import (
    available_field_names,
    build_documents,
    detect_id_field,
    resolve_id_field_explicit,
)
from core.opener import open_results
from core.pdf import ensure_weasyprint, html_to_pdf, make_pdf_filename, unique_output_path
from core.renderer import build_service_context, reconcile_template, render_template
from core.scanner import FileInfo, find_by_name_or_path, scan_data_files, scan_templates
from core.selector import (
    UserQuit,
    choose_documents,
    choose_from_files,
    choose_id_field_interactive,
    confirm_multiple,
    format_file_table,
    parse_document_choice,
    parse_index_spec,
    search_documents,
)


def setup_console() -> None:
    """Включить UTF-8 в консоли Windows, чтобы кириллица отображалась корректно."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, OSError, ValueError):
            pass
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Разобрать аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Генератор PDF из CSV/JSON по HTML-шаблону.",
    )
    parser.add_argument("--data", help="Файл данных (CSV или JSON), путь или имя файла")
    parser.add_argument("--template", help="HTML-шаблон, путь или имя файла")
    parser.add_argument(
        "--invoice",
        help="Invoice id одного или нескольких документов через запятую",
    )
    parser.add_argument("--id-field", dest="id_field", help="Явно задать поле-идентификатор")
    parser.add_argument("--json-root", dest="json_root", help="Ключ массива в JSON")
    parser.add_argument("--rows", help="Выбор по номерам: all, 3, 2-7, 1,4,9")
    parser.add_argument("--find", help="Отбор документов поиском")
    parser.add_argument("--output", help="Переопределить папку вывода")
    parser.add_argument("--no-open", action="store_true", help="Не открывать результат")
    parser.add_argument("--open-folder", action="store_true", help="Открыть папку вместо файлов")
    parser.add_argument("--keep-html", action="store_true", help="Сохранить промежуточный HTML")
    parser.add_argument("--list", action="store_true", dest="list_only", help="Показать найденные файлы и выйти")
    parser.add_argument("--yes", action="store_true", help="Не запрашивать подтверждение")
    return parser.parse_args(argv)


def print_not_found(kind: str, dirs: list[Path]) -> None:
    """Сообщение, если сканер ничего не нашёл."""
    listed = "\n".join(f"  • {path}" for path in dirs) or "  • (пути не заданы)"
    raise AppError(
        f"Не найдено {kind}.\nПросмотренные пути:\n{listed}\n"
        "Добавьте директорию в config.json (data_dirs / template_dirs)."
    )


def cmd_list(data_files: list[FileInfo], templates: list[FileInfo]) -> int:
    """Печать найденных файлов для флага --list."""
    print("Доступные файлы с данными:\n")
    if data_files:
        print(format_file_table(data_files))
    else:
        print("  (не найдено)")
    print("\nДоступные шаблоны:\n")
    if templates:
        print(format_file_table(templates))
    else:
        print("  (не найдено)")
    return 0


def resolve_data_file(
    spec: str | None,
    scanned: list[FileInfo],
    data_dirs: list[Path],
    project_root: Path,
) -> FileInfo:
    """Выбрать файл данных: из аргумента или интерактивно."""
    if spec:
        found = find_by_name_or_path(spec, scanned, project_root)
        if found is None:
            raise AppError(f"Файл данных не найден: {spec}")
        return found
    if not scanned:
        print_not_found("файлов данных (CSV/JSON)", data_dirs)
    return choose_from_files("Доступные файлы с данными:", scanned, [str(p) for p in data_dirs])


def resolve_template_file(
    spec: str | None,
    scanned: list[FileInfo],
    template_dirs: list[Path],
    project_root: Path,
) -> FileInfo:
    """Выбрать шаблон: из аргумента или интерактивно."""
    if spec:
        found = find_by_name_or_path(spec, scanned, project_root)
        if found is None:
            raise AppError(f"Шаблон не найден: {spec}")
        return found
    if not scanned:
        print_not_found("HTML-шаблонов", template_dirs)
    return choose_from_files("Доступные шаблоны:", scanned, [str(p) for p in template_dirs])


def resolve_id_field(
    records: list[dict[str, Any]],
    config: dict[str, Any],
    explicit: str | None,
) -> str:
    """Определить поле invoice id: аргумент, auto по кандидатам или ручной выбор."""
    if explicit:
        return resolve_id_field_explicit(records, explicit)

    configured = str(config.get("id_field", "auto"))
    if configured.lower() != "auto":
        return resolve_id_field_explicit(records, configured)

    candidates = list(config.get("id_field_candidates") or [])
    detected = detect_id_field(records, candidates)
    if detected:
        return detected

    fields = available_field_names(records)
    if not fields:
        print("В записях нет полей. Будет использован порядковый номер.")
        return "__row__"

    def refuse() -> str:
        print("Поле не выбрано — используется порядковый номер записи.")
        return "__row__"

    return choose_id_field_interactive(fields, refuse)


def apply_row_numbers(
    records: list[dict[str, Any]],
    id_field: str,
) -> None:
    """Если id берётся из номера строки — записать его в служебное поле."""
    if id_field != "__row__":
        return
    for index, record in enumerate(records, start=1):
        record["__row__"] = str(index)


def select_documents_cli(
    documents: list[Any],
    args: argparse.Namespace,
) -> list[Any]:
    """Выбор документов по аргументам --invoice / --rows / --find."""
    chosen = list(documents)

    if args.find:
        found = search_documents(chosen, args.find)
        if not found:
            raise AppError(f"По запросу {args.find!r} ничего не найдено.")
        chosen = found

    if args.invoice:
        selected: list[Any] = []
        for token in args.invoice.split(","):
            token = token.strip()
            if not token:
                continue
            result = parse_document_choice(token, documents)
            if not result.documents:
                raise AppError(result.message or f"Документ {token!r} не найден.")
            for doc in result.documents:
                if doc not in selected:
                    selected.append(doc)
        if args.find:
            ids = {d.invoice_id for d in chosen}
            selected = [d for d in selected if d.invoice_id in ids]
        chosen = selected

    if args.rows:
        indices = parse_index_spec(args.rows, len(documents))
        if indices is None:
            raise AppError(f"Некорректное значение --rows: {args.rows}")
        by_num = {d.row_num: d for d in documents}
        row_docs = [by_num[n] for n in indices if n in by_num]
        if args.invoice or args.find:
            ids = {d.invoice_id for d in chosen}
            chosen = [d for d in row_docs if d.invoice_id in ids]
        else:
            chosen = row_docs

    if not chosen:
        raise AppError("Не выбрано ни одного документа.")
    return chosen


def generate_one(
    doc: Any,
    template_html: str,
    template_path: Path,
    data_name: str,
    output_dir: Path,
    filename_pattern: str,
    font_dir: Path,
    font_family: str,
    keep_html: bool,
    date_stamp: str,
) -> tuple[Path, list[str]]:
    """Сформировать один PDF. Возвращает путь и предупреждения рендера."""
    service = build_service_context(
        invoice_id=doc.invoice_id,
        data_name=data_name,
        row_num=doc.row_num,
    )
    html_text, render_warnings = render_template(template_html, doc.record, service)
    filename = make_pdf_filename(
        filename_pattern,
        data_name=data_name,
        invoice_id=doc.invoice_id,
        row_num=doc.row_num,
        date=date_stamp,
    )
    output_path = unique_output_path(output_dir / filename)
    if keep_html:
        html_path = output_path.with_suffix(".html")
        html_path.write_text(html_text, encoding="utf-8")
    pdf_warnings = html_to_pdf(
        html_text,
        output_path,
        base_url=template_path.parent,
        font_dir=font_dir,
        font_family=font_family,
    )
    return output_path, render_warnings + pdf_warnings


def print_summary(created: list[Path], errors: list[str], output_dir: Path, project_root: Path) -> None:
    """Итоговая сводка после генерации."""
    print()
    print(f"Готово: создано {len(created)} PDF, ошибок {len(errors)}")
    print(f"Папка: {output_dir}")
    for path in created:
        try:
            rel = path.resolve().relative_to(project_root)
            shown = rel.as_posix()
        except ValueError:
            shown = str(path)
        print(f"  {shown}")
    if errors:
        print("Ошибки:")
        for item in errors:
            print(f"  [!] {item}")


def run(argv: list[str] | None = None) -> int:
    """Основной сценарий: сканирование, выбор, генерация, сводка."""
    args = parse_args(argv)
    project_root = get_project_root()
    config, created = load_config(project_root)
    if created:
        print(f"Создан файл конфигурации: {project_root / 'config.json'}")
        print("Можно изменить пути к данным и шаблонам и запустить снова.\n")

    recursive = bool(config.get("recursive", True))
    data_dirs = resolve_dir_list(list(config.get("data_dirs") or []), project_root)
    template_dirs = resolve_dir_list(list(config.get("template_dirs") or []), project_root)
    output_dir = resolve_path(args.output or str(config.get("output_dir") or "./output"), project_root)
    font_dir = resolve_path(str(config.get("font_dir") or "./fonts"), project_root)
    font_family = str(config.get("font_family") or "DejaVu Sans")

    data_files, data_warns = scan_data_files(data_dirs, recursive)
    templates, tmpl_warns = scan_templates(template_dirs, recursive)
    for warning in data_warns + tmpl_warns:
        print(f"[!] {warning}")

    if args.list_only:
        return cmd_list(data_files, templates)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AppError(f"Нет прав на запись в {output_dir}: {exc}") from None

    data_file = resolve_data_file(args.data, data_files, data_dirs, project_root)
    print()
    template_file = resolve_template_file(args.template, templates, template_dirs, project_root)

    json_root = args.json_root
    records, meta = load_data(data_file.path, config, json_root=json_root)
    if meta.get("format") == "CSV":
        print(
            f"CSV: кодировка {meta.get('encoding')}, "
            f"разделитель {meta.get('delimiter')!r}, движок {meta.get('engine')}."
        )
    skipped = int(meta.get("skipped") or 0)
    if skipped:
        print(f"[!] Пропущено элементов, которые не являются объектами: {skipped}.")
    if not records:
        raise AppError(f"В файле {data_file.name} нет записей для генерации.")

    id_field = resolve_id_field(records, config, args.id_field)
    apply_row_numbers(records, id_field)
    display_fields = list(config.get("display_fields") or [])
    documents, had_dupes = build_documents(records, id_field, display_fields)
    if had_dupes:
        print("[!] Значения invoice id не уникальны — к дублям добавлены суффиксы #2, #3, …")

    data_label = f"{data_file.name} ({data_file.kind}, записей: {len(documents)})"
    interactive_choice = not (args.invoice or args.rows or args.find)
    if interactive_choice:
        selected = choose_documents(documents, data_label, id_field)
    else:
        print(f"Файл: {data_label}")
        print(f"Поле идентификатора: {id_field}")
        selected = select_documents_cli(documents, args)

    if not confirm_multiple(len(selected), args.yes):
        print("Отменено.")
        return 0

    try:
        template_html = template_file.path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        template_html = template_file.path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise AppError(f"Не удалось прочитать шаблон {template_file.name}: {exc}") from None

    first = selected[0]
    service = build_service_context(
        invoice_id=first.invoice_id,
        data_name=data_file.path.stem,
        row_num=first.row_num,
    )
    print()
    for line in reconcile_template(template_html, first.record, service):
        print(line)
    print()
    ensure_weasyprint()

    created_paths: list[Path] = []
    errors: list[str] = []
    font_warned = False
    from datetime import datetime as dt

    date_stamp = dt.now().strftime("%Y-%m-%d")
    pattern = str(config.get("filename_pattern") or "{data_name}_{invoice_id}")

    for doc in selected:
        try:
            path, warnings = generate_one(
                doc,
                template_html,
                template_file.path,
                data_file.path.stem,
                output_dir,
                pattern,
                font_dir,
                font_family,
                args.keep_html,
                date_stamp,
            )
            created_paths.append(path)
            for warn in warnings:
                if "шрифт" in warn.lower() and font_warned:
                    continue
                print(f"[!] {warn}")
                if "шрифт" in warn.lower():
                    font_warned = True
        except AppError as exc:
            errors.append(f"{doc.invoice_id}: {exc}")
            print(f"[!] Ошибка документа {doc.invoice_id}: {exc}")

    auto_open = bool(config.get("auto_open", True))
    limit = int(config.get("auto_open_limit") or 5)
    open_warnings = open_results(
        created_paths,
        output_dir,
        auto_open=auto_open,
        auto_open_limit=limit,
        no_open=args.no_open,
        open_folder=args.open_folder,
    )
    for warn in open_warnings:
        print(f"[!] {warn}")

    print_summary(created_paths, errors, output_dir, project_root)
    return 1 if errors and not created_paths else 0


def main() -> int:
    """Точка входа с обработкой KeyboardInterrupt и ошибок без трассировки."""
    setup_console()
    try:
        return run()
    except UserQuit:
        print("Выход.")
        return 0
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        return 130
    except AppError as exc:
        print(str(exc))
        return 1
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code)
            return 1
        return int(exc.code or 0)


if __name__ == "__main__":
    sys.exit(main())
