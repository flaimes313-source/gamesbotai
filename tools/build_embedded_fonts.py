"""
Генерирует services/cards/fonts_embedded.py
с найденными TTF-шрифтами в base64.

Ищет в data/fonts/ любые файлы:
- Regular: DejaVuSans.ttf, NotoSans-Regular.ttf, Arial.ttf, arial.ttf
- Bold:    DejaVuSans-Bold.ttf, NotoSans-Bold.ttf, Arial-Bold.ttf, arialbd.ttf

Запуск:
    python tools/build_embedded_fonts.py
"""
import base64
import sys
from pathlib import Path


FONT_DIR = Path("data/fonts")
OUTPUT = Path("services/cards/fonts_embedded.py")

REGULAR_CANDIDATES = [
    "DejaVuSans.ttf",
    "NotoSans-Regular.ttf",
    "Arial.ttf",
    "arial.ttf",
]

BOLD_CANDIDATES = [
    "DejaVuSans-Bold.ttf",
    "NotoSans-Bold.ttf",
    "Arial-Bold.ttf",
    "arialbd.ttf",
    "Arial Bold.ttf",
]


def _find(candidates):
    for name in candidates:
        p = FONT_DIR / name
        if p.exists() and p.stat().st_size > 100_000:
            return p
    return None


def _b64_wrap(data_b64: str, width: int = 76) -> str:
    lines = [data_b64[i:i + width] for i in range(0, len(data_b64), width)]
    return "\n".join(f'    "{line}"' for line in lines)


def main() -> int:
    regular = _find(REGULAR_CANDIDATES)
    bold = _find(BOLD_CANDIDATES)

    if not regular:
        print("❌ Не найден regular шрифт в data/fonts/")
        print(f"   Ожидались: {REGULAR_CANDIDATES}")
        return 1

    if not bold:
        print("❌ Не найден bold шрифт в data/fonts/")
        print(f"   Ожидались: {BOLD_CANDIDATES}")
        return 1

    print(f"📖 Regular: {regular} ({regular.stat().st_size} bytes)")
    print(f"📖 Bold:    {bold} ({bold.stat().st_size} bytes)")

    regular_b64 = base64.b64encode(regular.read_bytes()).decode("ascii")
    bold_b64 = base64.b64encode(bold.read_bytes()).decode("ascii")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    content = f'''"""
Автоматически сгенерированный файл. НЕ редактировать вручную.
Шрифты вшиты в base64. Сгенерировано: tools/build_embedded_fonts.py
"""

import base64

DEJAVU_SANS_REGULAR_B64 = (
{_b64_wrap(regular_b64)}
)

DEJAVU_SANS_BOLD_B64 = (
{_b64_wrap(bold_b64)}
)


def get_regular_font_bytes() -> bytes:
    return base64.b64decode(DEJAVU_SANS_REGULAR_B64)


def get_bold_font_bytes() -> bytes:
    return base64.b64decode(DEJAVU_SANS_BOLD_B64)
'''

    OUTPUT.write_text(content, encoding="utf-8")
    size_kb = OUTPUT.stat().st_size // 1024
    print(f"✅ Записан {OUTPUT} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())