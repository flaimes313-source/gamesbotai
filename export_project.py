from pathlib import Path
import re

# ============================================================
# НАСТРОЙКИ
# ============================================================

# Папки, которые НЕ нужно выгружать
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
}

# Файлы, которые НЕ нужно выгружать
EXCLUDED_FILES = {
    ".env",
    "project_full.txt",
}

# Расширения файлов, которые будем включать
ALLOWED_EXTENSIONS = {
    ".py",
    ".json",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".sql",
    ".html",
    ".css",
    ".js",
    ".ts",
}

# Максимальный размер одного файла
# 2 MB достаточно для обычных файлов проекта
MAX_FILE_SIZE = 2 * 1024 * 1024

OUTPUT_FILE = "project_full.txt"


# ============================================================
# ЗАЩИТА СЕКРЕТОВ
# ============================================================

SECRET_PATTERNS = [
    # Telegram Bot Token
    (
        r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b",
        "[TELEGRAM_BOT_TOKEN_HIDDEN]"
    ),

    # API keys в стиле KEY=value
    (
        r'(?i)(api[_-]?key\s*=\s*)["\']?[^"\'\s]+',
        r'\1[API_KEY_HIDDEN]'
    ),

    # Tokens
    (
        r'(?i)(token\s*=\s*)["\']?[^"\'\s]+',
        r'\1[TOKEN_HIDDEN]'
    ),

    # Password
    (
        r'(?i)(password\s*=\s*)["\']?[^"\'\s]+',
        r'\1[PASSWORD_HIDDEN]'
    ),

    # Secret
    (
        r'(?i)(secret\s*=\s*)["\']?[^"\'\s]+',
        r'\1[SECRET_HIDDEN]'
    ),

    # YooKassa secret key
    (
        r'(?i)(yookassa[_-]?(secret|key)\s*=\s*)["\']?[^"\'\s]+',
        r'\1[YOOKASSA_SECRET_HIDDEN]'
    ),

    # GigaChat / AI keys
    (
        r'(?i)(gigachat[_-]?(api[_-]?)?key\s*=\s*)["\']?[^"\'\s]+',
        r'\1[GIGACHAT_KEY_HIDDEN]'
    ),
]


def hide_secrets(text):
    """
    Скрывает распространенные API-ключи, токены и пароли.
    """

    for pattern, replacement in SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text)

    return text


# ============================================================
# ПРОВЕРКА ФАЙЛА
# ============================================================

def should_include_file(path):
    """
    Проверяет, нужно ли добавлять файл в экспорт.
    """

    if path.name in EXCLUDED_FILES:
        return False

    if path.name.startswith(".env"):
        return False

    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return False

    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            print(f"Пропущен слишком большой файл: {path}")
            return False
    except OSError:
        return False

    return True


# ============================================================
# ПОИСК ФАЙЛОВ
# ============================================================

def get_project_files(root):
    """
    Возвращает список файлов проекта.
    """

    files = []

    for path in root.rglob("*"):

        if not path.is_file():
            continue

        # Проверяем, нет ли исключенной папки в пути
        relative_parts = path.relative_to(root).parts

        if any(part in EXCLUDED_DIRS for part in relative_parts):
            continue

        if should_include_file(path):
            files.append(path)

    return sorted(files)


# ============================================================
# ДЕРЕВО ПРОЕКТА
# ============================================================

def build_tree(root):
    """
    Создает текстовое дерево проекта.
    """

    lines = []

    def walk(directory, prefix=""):

        try:
            items = sorted(
                [
                    item for item in directory.iterdir()
                    if item.name not in EXCLUDED_DIRS
                    and item.name != OUTPUT_FILE
                ],
                key=lambda x: (x.is_file(), x.name.lower())
            )
        except PermissionError:
            return

        for index, item in enumerate(items):

            is_last = index == len(items) - 1

            connector = "└── " if is_last else "├── "

            lines.append(prefix + connector + item.name)

            if item.is_dir():

                new_prefix = prefix + ("    " if is_last else "│   ")

                walk(item, new_prefix)

    lines.append(root.name)
    walk(root)

    return "\n".join(lines)


# ============================================================
# ЧТЕНИЕ ФАЙЛА
# ============================================================

def read_file(path):
    """
    Читает файл в UTF-8.
    Если не получилось — пробует другую кодировку.
    """

    encodings = [
        "utf-8",
        "utf-8-sig",
        "cp1251",
    ]

    for encoding in encodings:

        try:

            text = path.read_text(
                encoding=encoding
            )

            return hide_secrets(text)

        except UnicodeDecodeError:
            continue

        except Exception as e:
            return f"[ОШИБКА ЧТЕНИЯ ФАЙЛА: {e}]"

    return "[НЕ УДАЛОСЬ ПРОЧИТАТЬ ФАЙЛ]"


# ============================================================
# СОЗДАНИЕ ЭКСПОРТА
# ============================================================

def export_project():

    root = Path.cwd()

    output_path = root / OUTPUT_FILE

    print()
    print("=" * 60)
    print("ЭКСПОРТ ПРОЕКТА")
    print("=" * 60)
    print()

    print(f"Корень проекта: {root}")
    print()

    # --------------------------------------------------------
    # Находим файлы
    # --------------------------------------------------------

    files = get_project_files(root)

    print(f"Найдено файлов: {len(files)}")
    print()

    # --------------------------------------------------------
    # Формируем результат
    # --------------------------------------------------------

    result = []

    result.append("=" * 80)
    result.append("ПОЛНАЯ СТРУКТУРА ПРОЕКТА")
    result.append("=" * 80)
    result.append("")

    result.append(build_tree(root))

    result.append("")
    result.append("")
    result.append("=" * 80)
    result.append("СОДЕРЖИМОЕ ФАЙЛОВ")
    result.append("=" * 80)
    result.append("")

    # --------------------------------------------------------
    # Добавляем содержимое каждого файла
    # --------------------------------------------------------

    for number, file_path in enumerate(files, start=1):

        relative_path = file_path.relative_to(root)

        print(
            f"[{number}/{len(files)}] {relative_path}"
        )

        result.append("")
        result.append("")
        result.append("#" * 80)
        result.append(f"FILE: {relative_path}")
        result.append("#" * 80)
        result.append("")

        content = read_file(file_path)

        result.append(content)

    # --------------------------------------------------------
    # Записываем результат
    # --------------------------------------------------------

    final_text = "\n".join(result)

    output_path.write_text(
        final_text,
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Статистика
    # --------------------------------------------------------

    size_kb = output_path.stat().st_size / 1024

    print()
    print("=" * 60)
    print("ГОТОВО")
    print("=" * 60)
    print()
    print(f"Файл: {output_path}")
    print(f"Файлов в экспорте: {len(files)}")
    print(f"Размер: {size_kb:.1f} KB")
    print()


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    export_project()