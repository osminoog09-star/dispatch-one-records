"""
Полная проверка сайта одной командой:  py server/qa_check.py

Проверяет не только «страница открылась», но и СОГЛАСОВАННОСТЬ данных —
именно на этом раньше ловили баги (звания на главной не совпадали с админкой).

Что проверяется:
  1. все маршруты (включая каждое дело/офицера/досье) отдают 200;
  2. внутренние ссылки в docs/ не битые, нет пустых страниц;
  3. в видимом тексте нет английских хвостов, сырых дат и mojibake;
  4. в базе нет дублей по external_id и записей без офицера;
  5. звания/отделы берутся ТОЛЬКО из Supabase (нет второго источника в шаблонах);
  6. живые Supabase-эндпоинты, которые дёргает сайт, отвечают.
Код возврата 1, если есть провалы.
"""
import io
import json
import os
import re
import sqlite3
import sys
import urllib.request
from urllib.parse import unquote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCS = os.path.join(ROOT, "docs")
BASE = "/dispatch-one-records/"
sys.path.insert(0, HERE)

SUPABASE_URL = "https://gwvqfiwdbviwoimvhdvg.supabase.co"
SUPABASE_KEY = "sb_publishable_gkXQmLngTvpGQfLFDk2YnA_nuv0krkk"

fails, warns = [], []


def ok(msg):
    print(f"  ✓ {msg}")


def bad(msg):
    fails.append(msg)
    print(f"  ✗ {msg}")


def warn(msg):
    warns.append(msg)
    print(f"  ! {msg}")


def check_routes():
    print("\n[1] Маршруты")
    from app.main import app
    from app import db
    urls = ["/", "/map", "/cases", "/court", "/shifts", "/citations", "/warnings", "/callouts",
            "/files", "/vehicles", "/tickets", "/admin", "/dictionaries", "/register", "/staff",
            "/support", "/launcher"]
    urls += [f"/case/{c['id']}" for c in db.list_cases(500)]
    urls += [f"/court/{c['id']}" for c in db.list_court_cases(500)]
    urls += [f"/shift/{s['id']}" for s in db.list_shifts(500)]
    urls += [f"/citation/{c['id']}" for c in db.list_citations(500)]
    urls += [f"/callout/{c['id']}" for c in db.list_callouts(500)]
    urls += ["/file/" + f["name"] for f in db.list_case_files(500)]
    urls += ["/vehicle/" + v["plate"] for v in db.list_vehicles(500)]
    with db.get_conn() as c:
        urls += ["/officer/" + r["callsign"] for r in
                 c.execute("SELECT callsign FROM officers WHERE callsign IS NOT NULL AND callsign!=''")]
    cl = app.test_client()
    broken = [(u, cl.get(u).status_code) for u in urls if cl.get(u).status_code != 200]
    if broken:
        bad(f"не 200: {broken[:5]}")
    else:
        ok(f"все {len(urls)} маршрутов отдают 200")


def check_docs():
    print("\n[2] Собранный сайт docs/")
    if not os.path.isdir(DOCS):
        return bad("папки docs/ нет — запусти export_static.py")

    def exists(u):
        u = unquote(u.split("#")[0].split("?")[0])
        if not u.startswith(BASE):
            return True
        p = os.path.join(DOCS, u[len(BASE):].strip("/"))
        return os.path.isfile(p) or (os.path.isdir(p) and os.path.isfile(os.path.join(p, "index.html")))

    junk = re.compile(r"Wobbler|arrested|Courtroom|Court-Appointed|CJA Panel|Private Counsel"
                      r"|Self-Represented|No contest|test-смена|Р[љ‘°]|T\d{2}:\d{2}:\d{2}\.\d+")
    pages = links = 0
    broken, empty, dirty = set(), [], set()
    for root, _, files in os.walk(DOCS):
        for f in files:
            if not f.endswith(".html"):
                continue
            pages += 1
            fp = os.path.join(root, f)
            txt = open(fp, encoding="utf-8", errors="ignore").read()
            rel = os.path.relpath(fp, DOCS)
            if len(txt) < 500:
                empty.append(rel)
            for href in re.findall(r'href="([^"]+)"', txt):
                if href.startswith(BASE):
                    links += 1
                    if not exists(href):
                        broken.add(href)
            vis = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", txt, flags=re.S)
            vis = re.sub(r"<[^>]+>", " ", vis)
            if junk.search(vis):
                dirty.add(rel)
    ok(f"страниц {pages}, внутренних ссылок {links}") if not broken else bad(f"битых ссылок: {len(broken)} — {list(broken)[:3]}")
    ok("нет пустых страниц") if not empty else bad(f"подозрительно пустые: {empty[:3]}")
    ok("нет мусора в видимом тексте") if not dirty else bad(f"мусор в: {list(dirty)[:3]}")


def check_db():
    print("\n[3] Целостность базы")
    c = sqlite3.connect(os.path.join(HERE, "data.db"))
    c.row_factory = sqlite3.Row

    def one(q, *a):
        return c.execute(q, a).fetchone()[0]
    for t in ("cases", "citations", "court_cases", "callouts"):
        d = one(f"SELECT COUNT(*) FROM (SELECT external_id FROM {t} "
                f"WHERE external_id IS NOT NULL GROUP BY external_id HAVING COUNT(*)>1)")
        ok(f"{t}: дублей нет") if not d else bad(f"{t}: дублей по external_id — {d}")
    orph = one("SELECT COUNT(*) FROM cases WHERE officer_id NOT IN (SELECT id FROM officers)")
    ok("дел без офицера нет") if not orph else bad(f"дел без офицера: {orph}")
    c.close()


def check_single_source():
    print("\n[4] Единый источник званий/отделов")
    tpl = os.path.join(HERE, "app", "templates")
    hits = []
    for f in os.listdir(tpl):
        if not f.endswith(".html"):
            continue
        txt = open(os.path.join(tpl, f), encoding="utf-8", errors="ignore").read()
        if re.search(r"\{\{\s*\w+\.(rank_label|department_label)\s*\}\}", txt):
            hits.append(f)
    if hits:
        bad(f"звание/отдел рендерятся из SQLite (второй источник) в: {hits} — "
            f"должно быть только .sb-rankdept из Supabase")
    else:
        ok("звание/отдел только из Supabase (.sb-rankdept)")


def check_supabase():
    print("\n[5] Supabase (то, что дёргает сайт)")
    def call(path, post=False):
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/{path}", data=b"{}" if post else None,
            method="POST" if post else "GET",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    for name, path, post in [
        ("справочник званий", "ranks?select=id&limit=1", False),
        ("справочник отделов", "departments?select=id&limit=1", False),
        ("профили офицеров", "officer_profiles?select=callsign&limit=1", False),
        ("реестр одобренных", "roster?select=callsign&limit=1", False),
        ("модерация", "pending_officers?select=callsign&limit=1", False),
        ("бейджи ролей", "rpc/public_staff_roles", True),
    ]:
        try:
            call(path, post)
            ok(name)
        except Exception as e:
            warn(f"{name}: недоступно ({str(e)[:60]})")


def main():
    print("=" * 60)
    print("  QA LAPD Records")
    print("=" * 60)
    check_routes()
    check_docs()
    check_db()
    check_single_source()
    check_supabase()
    print("\n" + "=" * 60)
    if fails:
        print(f"ПРОВАЛОВ: {len(fails)}")
        for f in fails:
            print("   ✗", f)
    else:
        print("ВСЁ ЧИСТО" + (f" (предупреждений: {len(warns)})" if warns else ""))
    print("=" * 60)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
