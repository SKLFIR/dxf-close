# -*- coding: utf-8 -*-
"""Генерация иконок приложения: PNG → .ico (Windows) и .icns (macOS).

    python tools/make_icon.py

Требует Pillow. .icns собирается через iconutil, то есть только на macOS;
на других системах шаг просто пропускается.
"""
import math
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "dxf_close", "assets")

BG = (245, 247, 250, 255)
INK = (26, 75, 140, 255)      # тот же синий, что и у замкнутых контуров в окне
FIX = (255, 140, 0, 255)      # оранжевый мостик


def draw(size):
    S = size * 4                     # рисуем с запасом и уменьшаем — сглаживание
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = S * 0.06
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=S * 0.22, fill=BG)

    cx = cy = S / 2
    r = S * 0.27
    w = max(2, int(S * 0.055))

    # разомкнутое кольцо: разрыв в правом верхнем секторе
    gap_a, gap_b = -58, -18
    d.arc([cx - r, cy - r, cx + r, cy + r], start=gap_b, end=360 + gap_a,
          fill=INK, width=w)

    def pt(deg):
        a = math.radians(deg)
        return cx + r * math.cos(a), cy + r * math.sin(a)

    p1, p2 = pt(gap_a), pt(gap_b)

    # мостик, закрывающий разрыв
    d.line([p1, p2], fill=FIX, width=int(w * 1.15))
    rr = w * 0.95
    for p in (p1, p2):
        d.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr],
                  outline=FIX, width=max(2, int(w * 0.45)))

    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    big = draw(1024)
    big.save(os.path.join(ASSETS, "icon_1024.png"))
    draw(256).save(os.path.join(ASSETS, "icon_256.png"))

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    draw(256).save(os.path.join(ASSETS, "icon.ico"),
                   sizes=[(s, s) for s in ico_sizes])
    print("готово: icon.ico, icon_256.png, icon_1024.png")

    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = os.path.join(ASSETS, "icon.iconset")
        shutil.rmtree(iconset, ignore_errors=True)
        os.makedirs(iconset)
        for s in (16, 32, 64, 128, 256, 512):
            draw(s).save(os.path.join(iconset, "icon_%dx%d.png" % (s, s)))
            draw(s * 2).save(os.path.join(iconset, "icon_%dx%d@2x.png" % (s, s)))
        subprocess.run(["iconutil", "-c", "icns", iconset,
                        "-o", os.path.join(ASSETS, "icon.icns")], check=True)
        shutil.rmtree(iconset, ignore_errors=True)
        print("готово: icon.icns")
    else:
        print("iconutil недоступен — .icns не собран (нужен macOS)")


if __name__ == "__main__":
    main()
