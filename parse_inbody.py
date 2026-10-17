"""Парсер PDF-отчётов InBody (DDX Fitness) в JSON.

Пропускает блоки «История состава тела» и «Обмен веществ / Суточная норма калорий /
Оптимальный вес / До оптимального веса».

    python parse_inbody.py результаты/261016_inbody_result.pdf   # JSON в stdout
    python parse_inbody.py результаты -o json                      # все PDF папки -> json/*.json
"""
import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

import pymupdf

STATUSES = ("Ниже нормы", "Выше нормы", "Норма")
CARDS = {"Вес": "weight", "Мышцы": "muscle", "Жир": "fat"}
ROWS = {**CARDS, "Вода": "water", "Белок": "protein", "Кости": "bones",
        "Висцеральный жир": "visceral_fat", "Индекс массы тела": "bmi", "Безжировая масса": "lean_mass"}
NUM = r"[+-]?\d+(?:[.,]\d+)?"


def num(s):
    s = s.replace(",", ".")
    return float(s) if "." in s else int(s)


def value(t):
    """'71.2 кг' -> {'value': 71.2, 'unit': 'кг'}"""
    m = re.fullmatch(rf"({NUM})\s*(.*)", t)
    if not m:
        raise ValueError(f"не число: {t!r}")
    return {"value": num(m[1]), "unit": m[2] or None}


def split_status(t):
    """'Жир Выше нормы' -> ('Жир', 'Выше нормы'); 'Вес' -> ('Вес', None)"""
    for s in STATUSES:
        if t == s or t.endswith(" " + s):
            return t[: -len(s)].strip(), s
    return t, None


def center(r):
    return (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2


def trend(drawings, r):
    """Знак изменения по векторной стрелке слева от числа: кончик ниже начала -> снижение."""
    for d in drawings:
        a = d["rect"]
        if a.width < 15 and abs(a.x1 - r.x0) < 4 and a.y0 < r.y1 and a.y1 > r.y0:
            start, tip = d["items"][0][1], d["items"][-1][1]
            return -1 if tip.y > start.y else 1
    raise ValueError(f"нет стрелки тренда у {r}")


def parse(path):
    page = pymupdf.open(path)[0]
    lines = [("".join(s["text"] for s in l["spans"]).strip(), pymupdf.Rect(l["bbox"]))
             for b in page.get_text("dict")["blocks"] for l in b.get("lines", [])]
    lines = [(t, r) for t, r in lines if t]
    texts = [t for t, _ in lines]

    head = dict(m.groups() for t in texts if (m := re.fullmatch(r"(Имя|Пол|Возраст|Рост|Дата) (.+)", t)))
    score = next((int(m[1]) for t in texts if (m := re.fullmatch(r"(\d+)/100", t))), None)

    # Шкалы: метка [статус], значение, '< a', 'a–b', '> b'
    body = {}
    for i, t in enumerate(texts):
        if re.fullmatch(rf"{NUM}–{NUM}", t):
            label, status = split_status(texts[i - 3])
            # ponytail: статус на шкале печатается только вне нормы, нет текста -> «Норма»
            body[ROWS[label]] = {**value(texts[i - 2]), "status": status or "Норма",
                                 "range": [num(x) for x in t.split("–")]}
    if len(body) != len(ROWS):
        raise ValueError(f"шкалы: найдено {sorted(body)}")

    # Карточки сверху: метка, статус, значение, [изменение со стрелкой — старый макет]
    drawings = None
    i = texts.index("Вес")
    for label, key in CARDS.items():
        if texts[i] != label:
            raise ValueError(f"ждали карточку {label!r}, а там {texts[i]!r}")
        body[key]["status"], body[key]["change"] = texts[i + 1], None
        i += 3
        if re.fullmatch(NUM, texts[i]):
            drawings = drawings or page.get_drawings()
            body[key]["change"] = num(texts[i]) * trend(drawings, lines[i][1])
            i += 1

    out = {
        "file": Path(path).name,
        "name": head["Имя"],
        "sex": head["Пол"],
        "age": int(head["Возраст"]),
        "height_cm": num(head["Рост"].removesuffix(" см")),
        "date": datetime.strptime(head["Дата"], "%d.%m.%y").date().isoformat(),
        "inbody_score": score,
        "body": body,
    }

    # Сегменты: подписи частей тела — картинки, поэтому раскладываем по положению на странице
    mid = page.rect.width / 2
    for title, key in (("Содержание мышц", "segmental_muscle"), ("Содержание Жира", "segmental_fat")):
        hr = next(r for t, r in lines if t == title)
        side = [(t, r) for t, r in lines if (center(r)[0] < mid) == (center(hr)[0] < mid)]
        total = next(t for t, r in side if t != title and abs(r.y0 - hr.y0) < 3)
        part = [(t, r) for t, r in side if r.y0 > hr.y1]
        segs = [(r, {"kg": value(t)["value"], "percent": None, "status": None}) for t, r in part if t.endswith(" кг")]
        for t, r in part:
            if t.endswith(" кг"):
                continue
            seg = min(segs, key=lambda s: math.dist(center(s[0]), center(r)))[1]
            if t.endswith("%"):
                seg["percent"] = value(t)["value"]
            else:
                seg["status"] = split_status(t)[1]
        if len(segs) != 5 or any(None in s.values() for _, s in segs):
            raise ValueError(f"{title}: {[s for _, s in segs]}")
        segs.sort(key=lambda s: center(s[0])[0])
        by_y = lambda s: center(s[0])[1]
        (la, ll), trunk, (ra, rl) = sorted(segs[:2], key=by_y), segs[2], sorted(segs[3:], key=by_y)
        out[key] = {"total_kg": value(total)["value"], "left_arm": la[1], "right_arm": ra[1],
                    "trunk": trunk[1], "left_leg": ll[1], "right_leg": rl[1]}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", type=Path, help="PDF-файлы или папки с ними")
    ap.add_argument("-o", "--out", type=Path, help="папка для .json (без неё — вывод в stdout)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    for pdf in (p for i in a.inputs for p in (sorted(i.glob("*.pdf")) if i.is_dir() else [i])):
        try:
            data = parse(pdf)
        except Exception as e:
            e.add_note(f"файл: {pdf}")
            raise
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
            (a.out / f"{pdf.stem}.json").write_text(text + "\n", encoding="utf-8")
            print(f"{pdf} -> {a.out / pdf.stem}.json")
        else:
            print(text)


if __name__ == "__main__":
    main()
