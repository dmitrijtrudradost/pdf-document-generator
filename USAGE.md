[К README](README.md)

## Быстрый старт

После установки зависимостей:

```bash
python generate.py --list
python generate.py --data data/example.json --template templates/chek_example.html --invoice INV-1001 --no-open
python generate.py --data example.csv --template chek_example.html --rows all --yes --no-open
```

При первом запуске без `config.json` файл создаётся автоматически со значениями по умолчанию.

## Примеры запуска

```bash
# Полностью интерактивно: меню файлов → шаблон → список чеков
python generate.py

# Показать найденные CSV/JSON и HTML, затем выйти
python generate.py --list

# Конкретный документ по invoice id
python generate.py --data data/example.json --template templates/chek_example.html --invoice INV-1001

# Несколько документов, без открытия PDF
python generate.py --data invoices.json --template chek.html --rows all --no-open

# Поиск по контрагенту и без подтверждения «Будет создано N PDF»
python generate.py --data aug.csv --find "Ромашка" --yes
```

Другие аргументы: `--id-field`, `--json-root`, `--rows 2-7`, `--rows 1,4,9`, `--output DIR`, `--open-folder`, `--keep-html`.

## Конфигурация

Файл `config.json` в корне проекта. Относительные пути считаются **от папки `generate.py`**, не от текущей рабочей директории. Можно указать несколько каталогов, в том числе абсолютных (`D:/Работа/Шаблоны`). Несуществующая папка даёт предупреждение, скрипт не падает.

Основные поля:

- `data_dirs` / `template_dirs` — где искать CSV, JSON и HTML;
- `output_dir` — куда писать PDF;
- `recursive` — обходить вложенные папки;
- `auto_open` / `auto_open_limit` — открывать результат (если файлов больше лимита — открывается папка);
- `csv_engine`: `auto` | `pandas` | `stdlib`;
- `csv_encoding` — кодировка CSV; `auto` — автоматический выбор;
- `csv_delimiter` — разделитель CSV; `auto` — автоматический выбор;
- `json_root` — ключ массива записей в JSON или `auto`;
- `font_dir` / `font_family` — папка шрифтов и используемое семейство;
- `display_fields` — поля, отображаемые в списке документов;
- `id_field` и `id_field_candidates` — поле номера документа;
- `filename_pattern` — шаблон имени, по умолчанию `{data_name}_{invoice_id}`.

## Структуры JSON

Кодировка `utf-8` (при ошибке — `utf-8-sig`). Вложенность **не разворачивается**. При `"json_root": "auto"` формат определяется сам; ключ можно задать в конфиге или флагом `--json-root`.

**1. Массив объектов** — список записей напрямую:

```json
[
  {"invoice_id": "INV-1001", "date": "2026-08-01", "total": 120000}
]
```

**2. Объект с массивом внутри** — берётся первый ключ, значение которого — список объектов:

```json
{
  "invoices": [
    {"invoice_id": "INV-1001", "date": "2026-08-01"}
  ]
}
```

**3. Словарь id → объект** — ключ становится `invoice_id`, если поля внутри нет:

```json
{
  "1024": {"date": "2026-08-01", "total": 120000},
  "1025": {"date": "2026-08-03", "total": 45000}
}
```

**4. Один объект** — одна запись (в том числе со вложенным `customer` и массивом `items`):

```json
{
  "invoice_id": "INV-1001",
  "customer": {"name": "ООО «Ромашка»"},
  "items": [{"name": "Аренда", "qty": 1, "price": 120000, "total": 120000}]
}
```

## Шаблоны

Синтаксис плейсхолдеров:

| Запись | Смысл |
|---|---|
| `{{ field }}` | плоское поле |
| `{{ customer.name }}` | вложенное поле |
| `{{ total\|money }}` | фильтр (`money`, `date`, `upper`, `lower`, `strip`) |
| `{{#items}} … {{/items}}` | цикл по массиву; внутри доступен `{{__index__}}` |
| `{{__invoice_id__}}`, `{{__date__}}`, `{{__datetime__}}`, `{{__data_name__}}`, `{{__row_num__}}` | служебные поля |

Значения из данных экранируются (`&`, `<`, `>`), разметка шаблона — нет.

В комплекте:

- `templates/chek_example.html`
- `data/example.csv` — плоские поля на русском (массив записей)
- `data/example.json` — массив объектов со вложенным `customer` и `items`
- `data/example_wrapped.json` — объект с массивом `invoices`
- `data/example_idmap.json` — словарь id → объект
- `data/example_single.json` — один объект-документ

Коды выхода: `0` — успех, `1` — ошибка, `130` — прерывание Ctrl+C.

## Тесты

Автоматические тесты проверяют загрузку CSV и JSON, обработку HTML-шаблона и выбор документа. Запуск из корня проекта:

```bash
python -m unittest discover -s tests -v
```

Тесты используют стандартную библиотеку Python. Генерация PDF и работа системных библиотек ими не проверяются.
