# -*- coding: utf-8 -*-
"""Тестовый DXF с заведомо известными дефектами — для проверки сшивки.

    python tools/make_test_dxf.py [выходной.dxf]

Кладёт четыре фигуры:
  1. квадрат с разрывом 0.30 мм между концами;
  2. восьмиугольник с разрывом 0.05 мм;
  3. квадрат, у которого одна сторона не дотянулась до середины другой (0.20 мм);
  4. целый треугольник — контроль, его трогать не должны.
"""
import math
import sys

import ezdxf

OUT = sys.argv[1] if len(sys.argv) > 1 else "test_gaps.dxf"

doc = ezdxf.new("R2007", setup=False)
msp = doc.modelspace()


def polyline(pts, closed=False):
    for i in range(len(pts) - (0 if closed else 1)):
        msp.add_line(pts[i], pts[(i + 1) % len(pts)])


# 1. квадрат с разрывом 0.30 мм в правом нижнем углу
polyline([(0, 0), (0, 20), (20, 20), (20, 0.30)])
msp.add_line((20, 0), (0.0, 0))

# 2. восьмиугольник с разрывом 0.05 мм
cx, cy, r = 40, 10, 9
pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
       for a in range(0, 360, 45)]
polyline(pts)                       # незамкнутый: не хватает последнего звена
last = pts[-1]
first = (pts[0][0], pts[0][1] + 0.05)
msp.add_line(last, first)

# 3. сторона не дотянулась до середины соседней на 0.20 мм (T-стык)
polyline([(60, 0), (60, 20), (80, 20), (80, 0), (60.20, 0)])

# 4. целый треугольник — контроль
polyline([(95, 0), (105, 20), (115, 0)], closed=True)

doc.saveas(OUT)
print("записан", OUT)
