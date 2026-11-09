[К README](README.md)

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

Шрифты DejaVu Sans уже включены в папку `fonts/`. Если они отсутствуют, скачайте их по ссылкам ниже и поместите в эту папку:

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
