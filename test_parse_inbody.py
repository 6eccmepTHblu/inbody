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


def test_auth():
    import http.client
    import json
    import tempfile
    import threading
    import time

    import bcrypt

    import app

    def req(method, path, body=None, cookie=None):
        c = http.client.HTTPConnection("127.0.0.1", srv.server_port)
        c.request(method, path, body, {"Cookie": cookie} if cookie else {})
        r = c.getresponse()
        r.read()
        return r.status, r.getheader("Location"), r.getheader("Set-Cookie")

    with tempfile.TemporaryDirectory() as tmp:
        app.PDFS, app.AUTH = Path(tmp), True
        app.FAILS.clear()
        srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            # пароль не задан — закрыто всё, кроме страницы входа, манифеста и иконок
            assert req("GET", "/api/data")[0] == 401
            assert req("POST", "/login", "password=x")[1] == "/login?error=nopass"
            (app.PDFS / "auth.json").write_text(json.dumps({"hash": bcrypt.hashpw(b"secret", bcrypt.gensalt(4)).decode()}))
            assert req("GET", "/")[:2] == (303, "/login")
            assert req("HEAD", "/")[:2] == (303, "/login")
            assert req("GET", "/figure/muscle.svg")[0] == 401
            assert req("POST", "/api/settings", "{}")[0] == 401
            for p in ("/login", "/manifest.webmanifest", "/icon-192.png", "/icon.svg"):
                assert req("GET", p)[0] == 200, p
            assert req("POST", "/login", "password=wrong")[1] == "/login?error=1"
            status, loc, cookie = req("POST", "/login", "username=slava&password=secret")
            assert (status, loc) == (303, "/") and all(a in cookie for a in ("HttpOnly", "Secure", "SameSite=Lax", "Max-Age=2592000"))
            session = cookie.split(";")[0]
            assert req("GET", "/api/data", cookie=session)[0] == 200
            assert "Max-Age=2592000" in req("GET", "/", cookie=session)[2]  # открытие сайта продлевает вход
            forged = session[:-1] + ("0" if session[-1] != "0" else "1")
            assert req("GET", "/api/data", cookie=forged)[0] == 401
            expired = f"{app.COOKIE}={app.make_token(app.load_hash(), int(time.time()) - 5)}"
            assert req("GET", "/api/data", cookie=expired)[0] == 401
            app.FAILS.extend([time.time()] * 10)  # 10 неудач подряд — вход на паузе даже с верным паролем
            assert req("POST", "/login", "password=secret")[1] == "/login?error=locked"
        finally:
            srv.shutdown()
            srv.server_close()
            app.AUTH = False
            app.FAILS.clear()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
