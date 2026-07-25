"""
Экспорт сайта в статические файлы для GitHub Pages (работает 24/7 бесплатно).

Рендерит все страницы (главная, дела, суд, смены, офицеры) в папку docs/,
переписывает ссылки под адрес вида https://<user>.github.io/<repo>/.

Запуск:  py export_static.py
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["STATIC_EXPORT"] = "1"   # скрыть dev-ссылки в публичной версии

from app.main import app          # noqa: E402
from app import db                # noqa: E402

REPO_NAME = os.environ.get("PAGES_BASE", "dispatch-one-records")
BASE = f"/{REPO_NAME}" if REPO_NAME else ""
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def rewrite(html):
    """Абсолютные ссылки → с префиксом репозитория; /path → /path/ (папочные index.html)."""
    if BASE:
        html = re.sub(r'((?:href|src)=")/(?!/)', r'\1' + BASE + '/', html)
    return html


def save(path_url, html):
    rel = path_url.strip("/")
    target_dir = os.path.join(OUT, rel) if rel else OUT
    os.makedirs(target_dir, exist_ok=True)
    with open(os.path.join(target_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(rewrite(html))


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)

    urls = ["/", "/cases", "/court", "/shifts", "/citations", "/register"]
    for c in db.list_cases(500):
        urls.append(f"/case/{c['id']}")
    for c in db.list_court_cases(500):
        urls.append(f"/court/{c['id']}")
    for s in db.list_shifts(500):
        urls.append(f"/shift/{s['id']}")
    for o in db.list_officers_with_stats():
        urls.append(f"/officer/{o['callsign']}")

    client = app.test_client()
    ok = 0
    for u in urls:
        r = client.get(u)
        if r.status_code == 200:
            save(u, r.get_data(as_text=True))
            ok += 1
        else:
            print(f"[skip] {u} -> {r.status_code}")

    # статика (css/js) и скриншоты
    src_static = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "static")
    shutil.copytree(src_static, os.path.join(OUT, "static"), dirs_exist_ok=True)
    shots = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
    if os.path.isdir(shots):
        shutil.copytree(shots, os.path.join(OUT, "screenshots"), dirs_exist_ok=True)

    # чтобы GitHub Pages не обрабатывал файлы через Jekyll
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    print(f"Экспортировано страниц: {ok} -> {OUT}")


if __name__ == "__main__":
    main()
