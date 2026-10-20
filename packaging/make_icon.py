"""Gera legendas.ico (o mesmo desenho do icon.svg da página) em vários tamanhos."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

TEAL = (14, 107, 104, 255)
WHITE = (255, 255, 255, 255)


def draw(size: int) -> Image.Image:
    s = size / 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1 * s, 5 * s, 31 * s, 27 * s], radius=3 * s, fill=TEAL)
    d.rounded_rectangle([6 * s, 18 * s, 26 * s, 21 * s], radius=1.5 * s, fill=WHITE)
    d.rounded_rectangle([9 * s, 22.5 * s, 23 * s, 25 * s], radius=1.25 * s, fill=WHITE)
    return img


def main(out: str) -> None:
    big = draw(256)
    big.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"ícone: {Path(out).resolve()}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "legendas.ico")
