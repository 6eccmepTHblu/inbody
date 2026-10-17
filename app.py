"""Веб-дашборд по PDF InBody: python app.py [порт] -> http://127.0.0.1:8000

PDF из папки «результаты» разбираются на лету (с кэшем по mtime): положил новый — обнови страницу.
"""
import functools
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymupdf

from parse_inbody import parse

ROOT = Path(__file__).parent
PDFS = ROOT / "результаты"
PANEL = "#f0f7f7"  # фон квадрантов с фигурой в новом макете
STATUS_FILLS = {"#12b76a", "#ff7d20", "#12d8d8"}  # плашки процентов: их рисует страница под выбранный замер


@functools.lru_cache(maxsize=None)
def parse_cached(path, mtime):
    return parse(path)


def records():
    data, errors = [], []
    for p in sorted(PDFS.glob("*.pdf")):
        try:
            data.append(parse_cached(p, p.stat().st_mtime))
        except Exception as e:
            errors.append(f"{p.name}: {e}")
    return {"records": sorted(data, key=lambda d: d["date"]), "errors": errors}


def hexc(c):
    return "#%02x%02x%02x" % tuple(round(x * 255) for x in c)


def path_d(items):
    out, cur = [], None
    for op, *pts in items:
        if op == "re":
            r = pts[0]
            out.append(f"M{r.x0:.2f} {r.y0:.2f}H{r.x1:.2f}V{r.y1:.2f}H{r.x0:.2f}Z")
            cur = None
        elif op == "qu":
            q = pts[0]
            out.append("M" + "L".join(f"{p.x:.2f} {p.y:.2f}" for p in (q.ul, q.ur, q.lr, q.ll)) + "Z")
            cur = None
        else:  # 'l' / 'c': первая точка — начало сегмента
            if cur != pts[0]:
                out.append(f"M{pts[0].x:.2f} {pts[0].y:.2f}")
            out.append(("L" if op == "l" else "C") + " ".join(f"{p.x:.2f} {p.y:.2f}" for p in pts[1:]))
            cur = pts[-1]
    return "".join(out)


@functools.lru_cache(maxsize=None)
def figures(path, mtime):
    """Фигуры тела из PDF нового макета -> {'muscle': svg, 'fat': svg}; None для старого макета."""
    page = pymupdf.open(path)[0]
    # Уровни >= 5 — белое «свечение» вокруг фигуры под soft mask: без маски в SVG это чёрный прямоугольник
    drawings = [d for d in page.get_drawings(extended=True) if d["type"] not in ("clip", "group") and d["level"] < 5]
    panels = [d["rect"] for d in drawings if d.get("fill") and hexc(d["fill"]) == PANEL]
    if not panels:
        return None
    mid = page.rect.width / 2
    out = {}
    for key, left in (("muscle", True), ("fat", False)):
        box = functools.reduce(lambda a, b: a | b, [r for r in panels if (r.x0 < mid) == left])
        els = []
        for d in drawings:
            fill = d["fill"] and hexc(d["fill"]) if "f" in d["type"] else None
            if not d["rect"].intersects(box) or fill in STATUS_FILLS:
                continue
            a = [f'd="{path_d(d["items"])}{"Z" if d.get("closePath") else ""}"', f'fill="{fill or "none"}"']
            if fill and d.get("fill_opacity", 1) < 1:
                a.append(f'fill-opacity="{d["fill_opacity"]:.2f}"')
            if fill and d.get("even_odd"):
                a.append('fill-rule="evenodd"')
            if "s" in d["type"] and d.get("color"):
                cap = d.get("lineCap") or 0
                cap = int(cap[0] if isinstance(cap, (tuple, list)) else cap)
                a += [f'stroke="{hexc(d["color"])}"', f'stroke-width="{d.get("width") or 1:.2f}"',
                      f'stroke-linecap="{("butt", "round", "square")[cap]}"',
                      f'stroke-linejoin="{("miter", "round", "bevel")[int(d.get("lineJoin") or 0)]}"']
                if d.get("stroke_opacity", 1) < 1:
                    a.append(f'stroke-opacity="{d["stroke_opacity"]:.2f}"')
            els.append(f"<path {' '.join(a)}/>")
        out[key] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box.x0:.2f} {box.y0:.2f} '
                    f'{box.width:.2f} {box.height:.2f}">{"".join(els)}</svg>')
    return out


def figure(key):
    for p in sorted(PDFS.glob("*.pdf"), reverse=True):  # свежий PDF нового макета
        if figs := figures(p, p.stat().st_mtime):
            return figs[key]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def do_GET(self):
        if self.path == "/api/data":
            self.send(json.dumps(records(), ensure_ascii=False), "application/json")
        elif self.path in ("/figure/muscle.svg", "/figure/fat.svg"):
            svg = figure(self.path.removeprefix("/figure/").removesuffix(".svg"))
            self.send(svg, "image/svg+xml") if svg else self.send_error(404, "нет PDF нового макета")
        else:
            super().do_GET()

    def send(self, text, ctype):
        body = text.encode()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
