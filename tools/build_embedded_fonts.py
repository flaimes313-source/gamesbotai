"""
Генерирует services/cards/fonts_embedded.py
с шрифтами DejaVuSans и DejaVuSans-Bold, вшитыми в base64.

Запуск:
    python tools/build_embedded_fonts.py

Требует наличия файлов:
    data/fonts/DejaVuSans.ttf
    data/fonts/DejaVuSans-Bold.ttf
"""
import base64
import os
import sys
from pathlib import Path


FONT_REGULAR = Path("data/fonts/DejaVuSans.ttf")
FONT_BOLD = Path("data/fonts/DejaVuSans-Bold.ttf")
OUTPUT = Path("services/cards/fonts_embedded.py")


def _b64_wrap(data_b64: str, width: int = 76) -> str:
    """Разбивает длинную строку base64 на куски по width символов (PEP8)."""
    lines = [data_b64[i:i + width] for i in range(0, len(data_b64), width)]
    return "\n".join(f'    "{line}"' for line in lines)


def main() -> int:
    if not FONT_REGULAR.exists():
        print(f"❌ Не найден: {FONT_REGULAR}")
        return 1
    if not FONT_BOLD.exists():
        print(f"❌ Не найден: {FONT_BOLD}")
        return 1

    print(f"📖 Читаю {FONT_REGULAR} ({FONT_REGULAR.stat().st_size} bytes)")
    regular_b64 = base64.b64encode(FONT_REGULAR.read_bytes()).decode("ascii")

    print(f"📖 Читаю {FONT_BOLD} ({FONT_BOLD.stat().st_size} bytes)")
    bold_b64 = base64.b64encode(FONT_BOLD.read_bytes()).decode("ascii")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    content = f'''"""
Автоматически сгенерированный файл. НЕ редактировать вручную.

Шрифты DejaVu Sans (Regular + Bold), вшитые в base64.
Позволяет генерировать карточки с кириллицей на любом хостинге,
включая BotHost, без необходимости складывать TTF-файлы рядом.

Сгенерировано: tools/build_embedded_fonts.py
Лицензия DejaVu: Bitstream Vera + Public Domain дополнения.
"""

import base64

DEJAVU_SANS_REGULAR_B64 = (
{_b64_wrap(regular_b64)}
)

DEJAVU_SANS_BOLD_B64 = (
{_b64_wrap(bold_b64)}
)


def get_regular_font_bytes() -> bytes:
    """Возвращает байты DejaVu Sans Regular."""
    return base64.b64decode(DEJAVU_SANS_REGULAR_B64)


def get_bold_font_bytes() -> bytes:
    """Возвращает байты DejaVu Sans Bold."""
    return base64.b64decode(DEJAVU_SANS_BOLD_B64)
'''

    OUTPUT.write_text(content, encoding="utf-8")
    size_kb = OUTPUT.stat().st_size // 1024
    print(f"✅ Записан {OUTPUT} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())