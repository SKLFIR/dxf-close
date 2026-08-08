# -*- coding: utf-8 -*-
"""Окно: чертёж с зумом, поле радиуса сшивки, сохранение результата."""
import os
import sys

from . import core


def run(dxf_path=None, tol0=0.1):
    import tkinter as tk
    from tkinter import filedialog, messagebox
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure
    from matplotlib.collections import LineCollection

    root = tk.Tk()
    root.title("Замыкание контуров DXF")
    root.geometry("1200x900")
    _set_window_icon(root)

    state = {"dwg": None, "res": None, "focus": 0, "layer_vars": {}}

    # ------------------------------------------------------------ панель
    top = tk.Frame(root, padx=8, pady=6)
    top.pack(fill="x")

    tk.Label(top, text="Радиус сшивки, мм:").pack(side="left")
    tol_var = tk.StringVar(value="%g" % tol0)
    entry = tk.Entry(top, textvariable=tol_var, width=8)
    entry.pack(side="left", padx=(4, 2))

    def bump(delta):
        try:
            v = float(tol_var.get().replace(",", "."))
        except ValueError:
            v = 0.0
        tol_var.set("%g" % max(0.0, round(v + delta, 4)))
        recompute()

    tk.Button(top, text="−", width=2, command=lambda: bump(-0.05)).pack(side="left")
    tk.Button(top, text="+", width=2, command=lambda: bump(+0.05)).pack(side="left", padx=(0, 10))
    tk.Button(top, text="Пересчитать", command=lambda: recompute()).pack(side="left")
    tk.Button(top, text="Открыть DXF…", command=lambda: open_file()).pack(side="left", padx=6)
    tk.Button(top, text="Сохранить DXF…", command=lambda: save_file()).pack(side="left")
    tk.Button(top, text="К проблеме →", command=lambda: goto_problem()).pack(side="left", padx=6)
    tk.Button(top, text="Вписать", command=lambda: fit_view()).pack(side="left")

    show_bridges = tk.BooleanVar(value=True)
    show_open = tk.BooleanVar(value=True)
    keep_hatch = tk.BooleanVar(value=True)
    tk.Checkbutton(top, text="мостики", variable=show_bridges,
                   command=lambda: redraw(True)).pack(side="left", padx=(12, 0))
    tk.Checkbutton(top, text="висячие концы", variable=show_open,
                   command=lambda: redraw(True)).pack(side="left")
    tk.Checkbutton(top, text="штриховку в результат", variable=keep_hatch,
                   command=lambda: recompute()).pack(side="left")

    # ------------------------------------------------------------ слои
    layers_bar = tk.Frame(root, padx=8, pady=2)
    layers_bar.pack(fill="x")

    def rebuild_layers_bar():
        for w in layers_bar.winfo_children():
            w.destroy()
        state["layer_vars"] = {}
        dwg = state["dwg"]
        if not dwg:
            return
        tk.Label(layers_bar, text="Штриховка на слоях:", fg="#444").pack(side="left")
        for name, rec in sorted(dwg.layers.items(), key=lambda kv: -kv[1]["total"]):
            var = tk.BooleanVar(value=name in dwg.hatch_layers)
            state["layer_vars"][name] = var
            tk.Checkbutton(layers_bar, variable=var, command=lambda: recompute(),
                           text="%s (%d, сам по себе %.0f%%)"
                                % (name, rec["total"], 100 * rec["share"])).pack(side="left")

    status = tk.Label(root, text="Откройте DXF-файл.", justify="left", anchor="w",
                      font=("Menlo" if sys.platform == "darwin" else "Consolas", 11),
                      padx=8)
    status.pack(fill="x")

    # ------------------------------------------------------------ холст
    # нижние панели пакуются первыми, иначе холст вытесняет их за край окна
    tk.Label(root, fg="#666", anchor="w", padx=8, pady=2,
             text="колесо мыши — зум к курсору · перетаскивание — панорама · "
                  "двойной клик — вписать целиком · Enter — пересчитать").pack(side="bottom", fill="x")

    fig = Figure(figsize=(9, 8), dpi=100)
    ax = fig.add_subplot(111)
    ax.set_aspect("equal")
    canvas = FigureCanvasTkAgg(fig, master=root)

    bar = tk.Frame(root)
    bar.pack(side="bottom", fill="x")
    NavigationToolbar2Tk(canvas, bar).update()

    canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    def toolbar_busy():
        """Включён режим «Лупа»/«Рука» в панели — не мешаем ей, иначе вид едет дважды."""
        return bool(getattr(canvas.toolbar, "mode", ""))

    def on_scroll(event):
        if event.inaxes is not ax or event.xdata is None:
            return
        f = 1 / 1.15 if event.button == "up" else 1.15
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        cx, cy = event.xdata, event.ydata
        ax.set_xlim(cx + (x0 - cx) * f, cx + (x1 - cx) * f)
        ax.set_ylim(cy + (y0 - cy) * f, cy + (y1 - cy) * f)
        canvas.draw_idle()

    pan = {"anchor": None, "active": False}
    PAN_THRESHOLD = 4      # пикселей: пока не сдвинулись дальше, вид стоит на месте

    def on_press(event):
        if event.inaxes is not ax or toolbar_busy():
            return
        if event.dblclick:
            fit_view()
            return
        pan["anchor"] = (event.xdata, event.ydata, event.x, event.y,
                         ax.get_xlim(), ax.get_ylim())
        pan["active"] = False

    def on_motion(event):
        if pan["anchor"] is None or event.inaxes is not ax or event.xdata is None:
            return
        x0, y0, px, py, xl, yl = pan["anchor"]
        # короткий клик не должен таскать чертёж — двигаем только после порога
        if not pan["active"]:
            if abs(event.x - px) < PAN_THRESHOLD and abs(event.y - py) < PAN_THRESHOLD:
                return
            pan["active"] = True
        dx, dy = x0 - event.xdata, y0 - event.ydata
        ax.set_xlim(xl[0] + dx, xl[1] + dx)
        ax.set_ylim(yl[0] + dy, yl[1] + dy)
        canvas.draw_idle()

    def on_release(_event):
        pan["anchor"] = None
        pan["active"] = False

    canvas.mpl_connect("scroll_event", on_scroll)
    canvas.mpl_connect("button_press_event", on_press)
    canvas.mpl_connect("motion_notify_event", on_motion)
    canvas.mpl_connect("button_release_event", on_release)

    def fit_view():
        res = state["res"]
        if not res or (not res.contours and not res.hatch):
            return
        xs = [p[0] for xy, _, _ in res.contours for p in xy] + \
             [v[0] for p, q, _ in res.hatch for v in (p, q)]
        ys = [p[1] for xy, _, _ in res.contours for p in xy] + \
             [v[1] for p, q, _ in res.hatch for v in (p, q)]
        m = max(max(xs) - min(xs), max(ys) - min(ys)) * 0.03 + 1
        ax.set_xlim(min(xs) - m, max(xs) + m)
        ax.set_ylim(min(ys) - m, max(ys) + m)
        canvas.draw_idle()

    def goto_problem():
        """Зум к очередному незакрытому месту."""
        res = state["res"]
        if not res:
            return
        spots = list(res.open_ends)
        for xy, closed, _ in res.contours:
            if not closed and xy:
                spots.append(xy[0])
        if not spots:
            status.config(text=core.report(res, state["skipped"]) + "\n→ незакрытых мест нет")
            return
        i = state["focus"] % len(spots)
        state["focus"] = i + 1
        cx, cy = spots[i]
        r = 3.0
        ax.set_xlim(cx - r, cx + r)
        ax.set_ylim(cy - r, cy + r)
        canvas.draw_idle()
        status.config(text=core.report(res, state["skipped"]) +
                      "\n→ место %d из %d: (%.3f, %.3f)" % (i + 1, len(spots), cx, cy))

    # ------------------------------------------------------------ отрисовка
    def redraw(keep_view=False):
        res = state["res"]
        xl, yl = ax.get_xlim(), ax.get_ylim()
        ax.clear()
        ax.set_aspect("equal")
        ax.set_facecolor("white")
        if not res:
            canvas.draw_idle()
            return
        if res.hatch:
            ax.add_collection(LineCollection([(p, q) for p, q, _ in res.hatch],
                                             colors="#b9c2cc", linewidths=0.4))
        ok, bad = [], []
        for xy, closed, _ in res.contours:
            n = len(xy)
            tgt = ok if closed else bad
            for i in (range(n) if closed else range(n - 1)):
                tgt.append((xy[i], xy[(i + 1) % n]))
        if ok:
            ax.add_collection(LineCollection(ok, colors="#1a4b8c", linewidths=0.8))
        if bad:
            ax.add_collection(LineCollection(bad, colors="#d62728", linewidths=2.0))
        if show_bridges.get() and res.bridges:
            ax.add_collection(LineCollection(res.bridges, colors="#ff8c00", linewidths=2.5))
            ax.plot([p[0] for s in res.bridges for p in s],
                    [p[1] for s in res.bridges for p in s],
                    "o", color="#ff8c00", ms=4, mfc="none")
        if show_open.get() and res.open_ends:
            ax.plot([p[0] for p in res.open_ends], [p[1] for p in res.open_ends],
                    "o", color="#d62728", ms=9, mfc="none", mew=1.6)
        s = res.stats
        title = ("замкнутых %d · открытых %d · мостиков %d · висячих концов %d"
                 % (s.get("closed", 0), s.get("open", 0),
                    s.get("bridges", 0), s.get("loose_after", 0)))
        if s.get("hatch_lines"):
            title += " · штриховка %d линий" % s["hatch_lines"]
        ax.set_title(title)
        if keep_view:
            ax.set_xlim(xl)
            ax.set_ylim(yl)
            canvas.draw_idle()
        else:
            fit_view()

    def recompute(keep_view=True):
        dwg = state["dwg"]
        if dwg is None:
            return
        try:
            tol = float(tol_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Радиус", "Введите число, например 0.2")
            return
        status.config(text="считаю…")
        root.update_idletasks()
        marked = {name for name, var in state["layer_vars"].items() if var.get()}
        res = core.process(dwg, tol, marked)
        if not keep_hatch.get():
            res.hatch = []
            res.stats["hatch_lines"] = 0
        state["res"] = res
        state["focus"] = 0
        status.config(text=core.report(res, dwg.skipped))
        redraw(keep_view=keep_view)

    def load(path):
        status.config(text="читаю %s…" % os.path.basename(path))
        root.update_idletasks()
        try:
            dwg = core.read_dxf(path)
        except Exception as exc:
            messagebox.showerror("Не читается", "%s\n\n%s" % (path, exc))
            status.config(text="не удалось открыть файл")
            return
        if not dwg.raw_segs and not dwg.hatch_from_entities:
            messagebox.showwarning("Пусто", "В файле не нашлось линейной геометрии.")
            return
        state["dwg"] = dwg
        rebuild_layers_bar()
        root.title("Замыкание контуров DXF — %s" % os.path.basename(path))
        recompute(keep_view=False)

    def open_file():
        start = os.path.dirname(state["dwg"].path) if state["dwg"] else os.path.expanduser("~")
        p = filedialog.askopenfilename(title="Выберите DXF", initialdir=start,
                                       filetypes=[("DXF", "*.dxf"), ("Все файлы", "*.*")])
        if p:
            load(p)

    def save_file():
        res, dwg = state["res"], state["dwg"]
        if not res:
            messagebox.showinfo("Нечего сохранять", "Сначала откройте DXF.")
            return
        base = os.path.basename(core.default_out_path(dwg.path))
        p = filedialog.asksaveasfilename(title="Сохранить как", defaultextension=".dxf",
                                         initialfile=base,
                                         initialdir=os.path.dirname(dwg.path),
                                         filetypes=[("DXF", "*.dxf")])
        if not p:
            return
        try:
            core.save_dxf(res, dwg.doc, p)
        except Exception as exc:
            messagebox.showerror("Не сохранилось", str(exc))
            return
        msg = "Сохранено:\n%s\n\n%s" % (p, core.report(res))
        left = res.stats.get("open", 0)
        if left:
            msg += "\n\nОсталось %d открытых контуров — увеличьте радиус." % left
        messagebox.showinfo("Готово", msg)

    root.bind("<Return>", lambda e: recompute())

    if dxf_path:
        root.after(60, lambda: load(dxf_path))
    else:
        root.after(120, open_file)
    root.mainloop()


def _set_window_icon(root):
    """Иконка окна: на Windows .ico, иначе PNG через PhotoImage."""
    import tkinter as tk
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    try:
        if sys.platform == "win32":
            root.iconbitmap(os.path.join(here, "icon.ico"))
        else:
            img = tk.PhotoImage(file=os.path.join(here, "icon_256.png"))
            root.iconphoto(True, img)
            root._icon_ref = img          # иначе Tk освободит картинку
    except Exception:
        pass
