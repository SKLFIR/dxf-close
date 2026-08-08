# -*- coding: utf-8 -*-
"""
Ядро: чтение DXF, сшивка висячих концов в пределах радиуса, сборка замкнутых
контуров, запись результата. Без GUI — используется и окном, и командной строкой.
"""
import math
import os
from collections import Counter, defaultdict

import ezdxf
from ezdxf import path as ezpath

SAG = 0.01          # мм: точность спрямления дуг/сплайнов в отрезки
SNAP = 6            # знаков после запятой при поиске точно совпадающих концов
COLLINEAR = 0.001   # мм: допуск слияния точек, лежащих на одной прямой

SKIP_TYPES = ("TEXT", "MTEXT", "DIMENSION", "HATCH", "POINT", "ATTDEF", "ATTRIB",
              "LEADER", "MLEADER", "IMAGE", "WIPEOUT", "SOLID", "3DFACE")


# ---------------------------------------------------------------- геометрия
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_on_segment(p, a, b):
    """Расстояние от точки до отрезка и параметр проекции t в [0, 1]."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-18:
        return dist(p, a), 0.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    t = max(0.0, min(1.0, t))
    return dist(p, (a[0] + t * dx, a[1] + t * dy)), t


def dist_to_line(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < 1e-12:
        return dist(p, a)
    return abs(dx * (a[1] - p[1]) - (a[0] - p[0]) * dy) / L


class Grid:
    """Хеш по ячейкам для поиска ближайших без сторонних библиотек."""

    def __init__(self, cell):
        self.cell = max(cell, 1e-6)
        self.buckets = defaultdict(list)

    def add_point(self, p, payload):
        self.buckets[(int(p[0] // self.cell), int(p[1] // self.cell))].append(payload)

    def add_segment(self, a, b, payload):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for gx in range(int(x0 // self.cell), int(x1 // self.cell) + 1):
            for gy in range(int(y0 // self.cell), int(y1 // self.cell) + 1):
                self.buckets[(gx, gy)].append(payload)

    def near(self, p, rings=1):
        gx, gy = int(p[0] // self.cell), int(p[1] // self.cell)
        out = []
        for dx in range(-rings, rings + 1):
            for dy in range(-rings, rings + 1):
                out.extend(self.buckets.get((gx + dx, gy + dy), ()))
        return out


# ---------------------------------------------------------------- чтение DXF
def collect_segments(doc):
    """Вся геометрия модели → список отрезков (p0, p1, слой). Дуги спрямляются."""
    segs = []
    skipped = Counter()

    def walk(container):
        for e in container:
            t = e.dxftype()
            if t == "INSERT":
                try:
                    walk(e.virtual_entities())
                except Exception:
                    skipped[t] += 1
                continue
            if t in SKIP_TYPES:
                skipped[t] += 1
                continue
            try:
                pts = [(v.x, v.y) for v in ezpath.make_path(e).flattening(SAG)]
            except Exception:
                skipped[t] += 1
                continue
            layer = e.dxf.layer if e.dxf.hasattr("layer") else "0"
            for i in range(len(pts) - 1):
                if dist(pts[i], pts[i + 1]) > 1e-12:
                    segs.append((pts[i], pts[i + 1], layer))

    walk(doc.modelspace())
    return segs, skipped


def read_dxf(path):
    doc = ezdxf.readfile(path)
    segs, skipped = collect_segments(doc)
    return doc, segs, skipped


# ---------------------------------------------------------------- сшивка
class Result:
    def __init__(self):
        self.contours = []      # (точки, closed, слой)
        self.bridges = []       # (p0, p1) — отрезки, добавленные при сшивке
        self.open_ends = []     # точки, оставшиеся висячими
        self.stats = {}


def build(segs, tol, collinear=COLLINEAR):
    """Сшивает висячие концы в радиусе tol и собирает контуры.

    Радиус применяется ТОЛЬКО к висячим концам. Если сшивать всю геометрию
    подряд, крупный радиус схлопывает короткие отрезки (острия букв и веток)
    и рвёт контур там, где он был целым.
    """
    res = Result()
    if not segs:
        return res

    def key(p):
        return (round(p[0], SNAP), round(p[1], SNAP))

    node_id = {}
    node_xy = []

    def node(p):
        k = key(p)
        if k not in node_id:
            node_id[k] = len(node_xy)
            node_xy.append((float(k[0]), float(k[1])))
        return node_id[k]

    edges = []          # [узел_a, узел_b, слой]
    for a, b, layer in segs:
        na, nb = node(a), node(b)
        if na != nb:
            edges.append([na, nb, layer])

    def degrees():
        d = Counter()
        for na, nb, _ in edges:
            d[na] += 1
            d[nb] += 1
        return d

    deg = degrees()
    loose = [n for n, v in deg.items() if v == 1]
    res.stats["loose_before"] = len(loose)

    bridges = []
    if tol > 0 and loose:
        # --- 1. пары висячих концов: жадно, начиная с самых близких
        g = Grid(tol)
        for n in loose:
            g.add_point(node_xy[n], n)
        cand = []
        seen = set()
        for n in loose:
            for m in g.near(node_xy[n]):
                if m == n:
                    continue
                pair = (min(n, m), max(n, m))
                if pair in seen:
                    continue
                seen.add(pair)
                d = dist(node_xy[n], node_xy[m])
                if d <= tol:
                    cand.append((d, n, m))
        cand.sort()
        taken = set()
        for d, n, m in cand:
            if n in taken or m in taken:
                continue
            taken.add(n)
            taken.add(m)
            edges.append([n, m, "0"])
            bridges.append((node_xy[n], node_xy[m]))

        # --- 2. остальные висячие концы: привязка к телу ближайшего отрезка
        rest = [n for n in loose if n not in taken]
        if rest:
            gseg = Grid(max(tol, 1.0))
            for i, (na, nb, _) in enumerate(edges):
                gseg.add_segment(node_xy[na], node_xy[nb], i)
            splits = defaultdict(list)   # ребро -> [(t, узел)]
            for n in rest:
                p = node_xy[n]
                best = None
                for i in set(gseg.near(p)):
                    na, nb, _ = edges[i]
                    if na == n or nb == n:
                        continue
                    d, t = point_on_segment(p, node_xy[na], node_xy[nb])
                    if d <= tol and (best is None or d < best[0]):
                        best = (d, i, t)
                if best is None:
                    continue
                _, i, t = best
                na, nb, _ = edges[i]
                if t < 1e-9 or t > 1 - 1e-9:
                    m = na if t < 0.5 else nb
                    if m != n:
                        edges.append([n, m, "0"])
                        bridges.append((p, node_xy[m]))
                else:
                    a, b = node_xy[na], node_xy[nb]
                    proj = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
                    m = node(proj)
                    splits[i].append((t, m))
                    if m != n:
                        edges.append([n, m, "0"])
                        bridges.append((p, proj))
            for i, cuts in splits.items():
                na, nb, layer = edges[i]
                cuts.sort()
                chain = [na] + [m for _, m in cuts] + [nb]
                edges[i] = [chain[0], chain[1], layer]
                for j in range(1, len(chain) - 1):
                    edges.append([chain[j], chain[j + 1], layer])

    deg = degrees()
    res.open_ends = [node_xy[n] for n, v in deg.items() if v == 1]
    res.bridges = bridges

    # --- обход: собираем цепочки, на развилках идём максимально прямо
    adj = defaultdict(list)
    for i, (na, nb, _) in enumerate(edges):
        adj[na].append(i)
        adj[nb].append(i)
    used = [False] * len(edges)

    def other(i, n):
        na, nb, _ = edges[i]
        return nb if na == n else na

    def step(cur, prev):
        cand = [i for i in adj[cur] if not used[i]]
        if not cand:
            return None
        if prev is None:
            return cand[0]
        px, py = node_xy[prev]
        cx, cy = node_xy[cur]
        vx, vy = cx - px, cy - py
        n1 = math.hypot(vx, vy) or 1.0
        best, bestdot = None, -9e9
        for i in cand:
            ox, oy = node_xy[other(i, cur)]
            wx, wy = ox - cx, oy - cy
            n2 = math.hypot(wx, wy) or 1.0
            d = (vx * wx + vy * wy) / (n1 * n2)
            if d > bestdot:
                bestdot, best = d, i
        return best

    contours = []
    for s0 in range(len(edges)):
        if used[s0]:
            continue
        layer = edges[s0][2]
        used[s0] = True
        start = edges[s0][0]
        chain = [start, edges[s0][1]]
        prev, cur = chain[-2], chain[-1]
        while True:
            i = step(cur, prev)
            if i is None:
                break
            used[i] = True
            nxt = other(i, cur)
            chain.append(nxt)
            prev, cur = cur, nxt
            if nxt == start:
                break
        closed = chain[-1] == start
        if closed:
            chain.pop()
        else:
            prev, cur = chain[1], chain[0]
            while True:
                i = step(cur, prev)
                if i is None:
                    break
                used[i] = True
                nxt = other(i, cur)
                chain.insert(0, nxt)
                prev, cur = cur, nxt
                if nxt == chain[-1]:
                    chain.pop(0)
                    closed = True
                    break
        contours.append(([node_xy[n] for n in chain], closed, layer))

    # --- слияние точек, лежащих на одной прямой
    def simplify(xy, closed, tol_c):
        n = len(xy)
        if n < 3 or tol_c <= 0:
            return xy
        keep = [True] * n
        rng = range(n) if closed else range(1, n - 1)
        for i in rng:
            if dist_to_line(xy[i], xy[(i - 1) % n], xy[(i + 1) % n]) <= tol_c:
                keep[i] = False
        for i in range(n):
            if not keep[i] and not keep[(i - 1) % n]:
                keep[i] = True
        out = [xy[i] for i in range(n) if keep[i]]
        return out if len(out) >= (3 if closed else 2) else xy

    pts_before = sum(len(c[0]) for c in contours)
    res.contours = [(simplify(xy, cl, collinear), cl, lay) for xy, cl, lay in contours]
    res.stats.update(
        edges=len(edges),
        bridges=len(bridges),
        contours=len(res.contours),
        closed=sum(1 for c in res.contours if c[1]),
        open=sum(1 for c in res.contours if not c[1]),
        loose_after=len(res.open_ends),
        pts_before=pts_before,
        pts_after=sum(len(c[0]) for c in res.contours),
        perimeter=sum(dist(s[0], s[1]) for s in segs),
    )
    return res


# ---------------------------------------------------------------- запись
def save_dxf(res, src_doc, out_path):
    doc = ezdxf.new(dxfversion=src_doc.dxfversion, setup=False)
    for layer in src_doc.layers:
        name = layer.dxf.name
        if name not in doc.layers:
            try:
                doc.layers.add(name=name, color=layer.dxf.color)
            except Exception:
                pass
    try:
        doc.header["$INSUNITS"] = src_doc.header.get("$INSUNITS", 4)
    except Exception:
        pass
    msp = doc.modelspace()
    for xy, closed, layer in res.contours:
        if len(xy) < 2:
            continue
        pl = msp.add_lwpolyline(xy, format="xy", dxfattribs={"layer": layer})
        pl.closed = closed
    doc.saveas(out_path)
    return out_path


def default_out_path(src):
    base, ext = os.path.splitext(src)
    return base + "_замкнутый" + (ext or ".dxf")


def report(res, skipped=None):
    s = res.stats
    lines = [
        "отрезков: %d  (мостиков добавлено: %d)" % (s.get("edges", 0), s.get("bridges", 0)),
        "висячих концов: было %d → осталось %d" % (s.get("loose_before", 0), s.get("loose_after", 0)),
        "контуров: %d — замкнутых %d, открытых %d" % (s.get("contours", 0), s.get("closed", 0), s.get("open", 0)),
        "вершин: %d → %d" % (s.get("pts_before", 0), s.get("pts_after", 0)),
        "общая длина реза: %.2f мм" % s.get("perimeter", 0.0),
    ]
    if skipped:
        lines.append("пропущено (не геометрия): %s" % dict(skipped))
    return "\n".join(lines)
