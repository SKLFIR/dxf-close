# -*- coding: utf-8 -*-
"""Точка входа: окно по умолчанию, пакетный режим по --save."""
import argparse
import sys

from . import core


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="dxf-close",
        description="Замыкание контуров DXF: сшивает висячие концы в пределах "
                    "радиуса и собирает отрезки в замкнутые полилинии.")
    ap.add_argument("dxf", nargs="?", help="исходный DXF")
    ap.add_argument("-r", "--radius", type=float, default=0.1,
                    help="радиус сшивки висячих концов, мм (по умолчанию 0.1)")
    ap.add_argument("-o", "--out", help="куда сохранить (по умолчанию <имя>_замкнутый.dxf)")
    ap.add_argument("--save", action="store_true",
                    help="без окна: посчитать и сразу сохранить")
    ap.add_argument("--check", action="store_true",
                    help="без окна: только отчёт, ничего не записывать")
    ap.add_argument("--install-shortcut", action="store_true",
                    help="создать ярлык на рабочем столе")
    args = ap.parse_args(argv)

    if args.install_shortcut:
        from . import shortcut
        print("ярлык:", shortcut.create())
        return 0

    if args.save or args.check:
        if not args.dxf:
            ap.error("нужен путь к DXF")
        doc, segs, skipped = core.read_dxf(args.dxf)
        res = core.build(segs, args.radius)
        print(core.report(res, skipped))
        if args.save:
            out = args.out or core.default_out_path(args.dxf)
            core.save_dxf(res, doc, out)
            print("сохранено:", out)
        return 0

    from . import gui
    gui.run(args.dxf, args.radius)
    return 0


if __name__ == "__main__":
    sys.exit(main())
