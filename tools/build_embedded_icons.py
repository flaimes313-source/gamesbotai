"""
Генерирует services/cards/icons_data.py со встроенными в base64 PNG-иконками.

Запуск:
    python tools/build_embedded_icons.py

Требует наличия папки data/icons/ с PNG-файлами.
"""
import base64
import sys
from pathlib import Path


ICONS_DIR = Path("data/icons")
OUTPUT = Path("services/cards/icons_data.py")

# Список файлов, которые встраиваем
ICON_FILES = [
    # Характеристики
    "stat_charisma.png",
    "stat_humor.png",
    "stat_chaos.png",
    "stat_intellect.png",
    "stat_energy.png",
    "stat_creativity.png",
    # Достижения
    "ach_first_photo.png",
    "ach_first_share.png",
    "ach_friend_joined.png",
    "ach_first_test.png",
    "ach_five_tests.png",
    "ach_chaos_90.png",
    "ach_charisma_90.png",
    "ach_five_analyses.png",
    "ach_first_match.png",
    "ach_ten_messages.png",
    "ach_pro_first.png",
    "ach_default.png",
]


def _b64_wrap(data_b64: str, width: int = 76) -> str:
    """Разбивает длинную base64-строку на куски по width символов."""
    lines = [data_b64[i:i + width] for i in range(0, len(data_b64), width)]
    return "\n".join(f'    "{line}"' for line in lines)


def main() -> int:
    if not ICONS_DIR.exists():
        print(f"❌ Папка не найдена: {ICONS_DIR}")
        return 1

    missing = [f for f in ICON_FILES if not (ICONS_DIR / f).exists()]
    if missing:
        print(f"❌ Не найдены файлы: {missing}")
        return 1

    print(f"📖 Читаю {len(ICON_FILES)} иконок из {ICONS_DIR}")

    parts = []
    for fname in ICON_FILES:
        path = ICONS_DIR / fname
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        key = fname.replace(".", "_").upper()
        print(f"   {fname}: {len(data)} bytes → {len(b64)} base64")
        parts.append((key, b64))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # Формируем Python-файл
    body_lines = [
        '"""',
        "Автоматически сгенерированный файл. НЕ редактировать вручную.",
        "",
        "PNG-иконки для карточек, вшитые в base64.",
        "Сгенерировано: tools/build_embedded_icons.py",
        '"""',
        "",
        "import base64",
        "from typing import Optional",
        "",
    ]

    for key, b64 in parts:
        body_lines.append(f"{key} = (")
        body_lines.append(_b64_wrap(b64))
        body_lines.append(")")
        body_lines.append("")

    body_lines.append("")
    body_lines.append("def get_icon_bytes(name: str) -> Optional[bytes]:")
    body_lines.append('    """Возвращает байты иконки по ключу."""')
    body_lines.append("    value = globals().get(name)")
    body_lines.append("    if value is None:")
    body_lines.append("        return None")
    body_lines.append('    return base64.b64decode(value)')
    body_lines.append("")

    OUTPUT.write_text("\n".join(body_lines), encoding="utf-8")

    size_kb = OUTPUT.stat().st_size // 1024
    print(f"✅ Записан {OUTPUT} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())