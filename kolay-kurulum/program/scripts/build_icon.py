"""Create the multi-size Windows window icon from the original mergen logo."""
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'assets' / 'mergen-logo.png'
TARGET = ROOT / 'assets' / 'mergen.ico'
SIZES = (16, 24, 32, 48, 64, 128, 256)


def build() -> Path:
    logo = Image.open(SOURCE).convert('RGBA')
    side = max(logo.size)
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(logo, ((side - logo.width) // 2, (side - logo.height) // 2))
    canvas.save(TARGET, format='ICO', sizes=[(size, size) for size in SIZES])
    return TARGET


if __name__ == '__main__':
    print(build())
