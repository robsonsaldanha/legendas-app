"""Gera o ícone do programa (legendas.ico) e o ícone da página a partir do logo CNT.

O logo é largo (≈3:1); no ícone ele vai centralizado num quadrado escuro arredondado,
a mesma cor do tema do programa.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
LOGO = HERE / "assets" / "cnt-logo.png"
BG = (31, 35, 40, 255)


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=max(2, size // 5), fill=BG)
    logo = Image.open(LOGO).convert("RGBA")
    w = int(size * 0.86)
    h = int(logo.height * w / logo.width)
    logo = logo.resize((w, h), Image.LANCZOS)
    img.alpha_composite(logo, ((size - w) // 2, (size - h) // 2))
    return img


def main(out: str) -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw(s) for s in sizes]
    imgs[-1].save(out, sizes=[(s, s) for s in sizes], append_images=imgs[:-1])
    print(f"ícone: {Path(out).resolve()}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "legendas.ico")
