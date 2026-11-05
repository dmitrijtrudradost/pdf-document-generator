# Генератор PDF-документов

Автоматическая генерация PDF-документов из вашей таблицы — 
счета, акты, чеки, договоры

Настрою скрипт, который берёт данные из вашего Excel/CSV или JSON 
и превращает каждую строку в готовый PDF по вашему фирменному бланку — 
с логотипом, печатью, корректной кириллицей и аккуратными таблицами. 
Подойдёт бухгалтерам, юристам, агентствам и интернет-магазинам, 
которые каждый месяц вручную собирают десятки однотипных документов 
в Word. Вместо часа копипаста — выбираете нужный документ по номеру 
в меню, и PDF готов за секунду; можно сгенерировать всю пачку одной 
командой. Работает на Windows и macOS, без подписок и облаков — 
все данные остаются на вашем компьютере.



**Версия 1.0**

Консольная утилита на Python 3.10+: подставляет данные из CSV или JSON в HTML-шаблон и сохраняет готовые счета, акты и чеки в PDF.

Работает на Windows 10/11 и macOS без правок кода.

## Возможности

- Интерактивный режим: выбор файла данных, шаблона и конкретного документа через меню.
- Запуск с аргументами командной строки — без прохождения меню.
- CSV (стандартный `csv` или опционально pandas) и JSON.
- Четыре структуры JSON, вложенные поля `{{ customer.name }}`, циклы `{{#items}}`, фильтры `|money`, `|date`.
- Кириллица в PDF через DejaVu Sans.
- Автоматическое открытие готового файла в системной программе.

## Установка

Нужен **Python 3.10 или новее**.

```bash
cd путь/к/проекту
python -m venv .venv
```

Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Зависимость по умолчанию одна: `weasyprint`. Pandas не обязателен; если его нет, CSV читается стандартной библиотекой.

### Windows: GTK для WeasyPrint

WeasyPrint на Windows нуждается в GTK. Без него импорт библиотеки падает с ошибкой про `libgobject` / Cairo.

1. Скачайте установщик **GTK3 Runtime** для Windows:
   [GTK for Windows Runtime Environment Installer](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases)
2. Установите, отметив пункт добавления GTK в `PATH`.
3. **Полностью закройте и откройте** терминал (или Cursor), затем повторите запуск.

Альтернатива: пакет [MSYS2](https://www.msys2.org/) с пакетами Pango/Cairo.

### macOS: системные библиотеки

```bash
brew install pango gdk-pixbuf libffi
```

Затем `pip install -r requirements.txt`.

### Шрифты DejaVu Sans

Положите два файла в папку `fonts/`:

| Файл | Начертание |
|---|---|
| `fonts/DejaVuSans.ttf` | обычное |
| `fonts/DejaVuSans-Bold.ttf` | жирное |

Где взять:

- Сайт проекта: https://dejavu-fonts.github.io/
- Архив 2.37: https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip  
  Внутри архива: `dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf` и `DejaVuSans-Bold.ttf`.

Если файлов нет, скрипт предупредит и продолжит со стандартным `sans-serif` (кириллица в PDF может превратиться в «квадраты»).

В `config.json` параметр `font_family` можно сменить на `Roboto` или `Liberation Sans` — соответствующие `.ttf` должны лежать в той же папке `fonts/`.

## Быстрый старт

После установки зависимостей и шрифтов:

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


## Структура проекта

```
generate.py              точка входа
core/                    конфиг, сканер, загрузчики, меню, рендер, PDF
templates/               HTML-шаблоны
data/                    CSV и JSON
fonts/                   DejaVuSans.ttf, DejaVuSans-Bold.ttf
output/                  готовые PDF
config.json
requirements.txt
```

Коды выхода: `0` — успех, `1` — ошибка, `130` — прерывание Ctrl+C.
