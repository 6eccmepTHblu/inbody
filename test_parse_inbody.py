"""Проверка парсера на PDF из папки «результаты»: python test_parse_inbody.py"""
from pathlib import Path

from parse_inbody import parse

DIR = Path(__file__).parent / "результаты"


def test_old_layout_with_trends():
    d = parse(DIR / "260409_inbody_result.pdf")
    assert d["date"] == "2026-04-09" and d["inbody_score"] is None
    assert [d["body"][k]["change"] for k in ("weight", "muscle", "fat")] == [-0.3, 0.5, -1.7]
    assert d["body"]["visceral_fat"] == {"value": 4, "unit": None, "status": "Ниже нормы", "range": [7, 10]}
    assert d["segmental_muscle"]["right_leg"] == {"kg": 9.52, "percent": 105.4, "status": "Норма"}
    assert d["segmental_fat"]["trunk"] == {"kg": 5.5, "percent": 127.69, "status": "Выше нормы"}


def test_new_layout_with_score():
    d = parse(DIR / "261016_inbody_result.pdf")
    assert d["date"] == "2026-10-16" and d["inbody_score"] == 74
    assert d["body"]["fat"] == {"value": 21, "unit": "%", "status": "Выше нормы", "range": [10, 20], "change": None}
    assert d["segmental_muscle"]["left_arm"] == {"kg": 2.79, "percent": 85, "status": "Норма"}
    assert d["segmental_fat"]["left_leg"] == {"kg": 2.3, "percent": 133.16, "status": "Выше нормы"}


def test_all_statuses_match_ranges():
    for pdf in DIR.glob("*.pdf"):
        for k, v in parse(pdf)["body"].items():
            lo, hi = v["range"]
            expected = "Ниже нормы" if v["value"] < lo else "Выше нормы" if v["value"] > hi else "Норма"
            assert v["status"] == expected, (pdf.name, k, v)


def test_api():
    import json
    import tempfile
    import threading
    import urllib.request
    from urllib.error import HTTPError

    import app

    def post(body, path="/api/upload"):
        try:
            with urllib.request.urlopen(urllib.request.Request(url.replace("/api/upload", path), body, method="POST")) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, json.load(e)

    with tempfile.TemporaryDirectory() as tmp:
        app.PDFS = Path(tmp) / "pdfs"
        srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_port}/api/upload"
        pdf = (DIR / "261016_inbody_result.pdf").read_bytes()
        try:
            assert post(b"not a pdf")[0] == 400
            assert post(b"%PDF-1.4 broken")[0] == 400
            assert post(pdf) == (201, {"date": "2026-10-16"})
            assert post(pdf)[0] == 409
            assert [p.name for p in app.PDFS.iterdir()] == ["261016_inbody_result.pdf"]
            assert app.records()["settings"] == {}
            for bad in (b"", b"[]", b'{"start": 5}', b'{"start": "20260916"}', b'{"start": "2026-02-30"}'):
                assert post(bad, "/api/settings")[0] == 400, bad
            assert post(b'{"start": "2026-09-16"}', "/api/settings") == (200, {"start": "2026-09-16"})
            assert app.records()["settings"] == {"start": "2026-09-16"}
            assert post(b'{"start": null}', "/api/settings") == (200, {})
            assert app.records()["settings"] == {}
            # ручные записи (с фото): подхватываются, дубль даты пропускается, загрузка PDF за ту же дату — 409
            (app.PDFS / "manual").mkdir()
            rec = parse(DIR / "260409_inbody_result.pdf")
            (app.PDFS / "manual" / "a.json").write_text(json.dumps({**rec, "file": "a.jpg"}), encoding="utf-8")
            (app.PDFS / "manual" / "b.json").write_text(json.dumps({**rec, "file": "b.jpg", "date": "2026-10-16"}), encoding="utf-8")
            d = app.records()
            assert [r["date"] for r in d["records"]] == ["2026-04-09", "2026-10-16"] and "b.jpg" in d["errors"][0]
            assert post((DIR / "260409_inbody_result.pdf").read_bytes())[0] == 409
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
