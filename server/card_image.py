"""
Рендер карточки-документа (арест/суд/штраф/вызов) в PNG.
Запускает Flask локально, открывает страницу карточки в headless-браузере,
снимает элемент #doc — получается та же красивая карточка, что на сайте, картинкой.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


_server_started = False
_port = 8747


def _ensure_server():
    """Поднимает Flask в фоне один раз (для рендера карточек)."""
    global _server_started
    if _server_started:
        return
    from app.main import app
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    def run():
        app.run(host="127.0.0.1", port=_port, debug=False, use_reloader=False)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    # ждём готовности
    import urllib.request
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{_port}/", timeout=1)
            _server_started = True
            return
        except Exception:
            time.sleep(0.25)
    _server_started = True   # всё равно попробуем


# путь на карточку по типу
_PATHS = {
    "arrest": "/case/{id}",
    "citation": "/citation/{id}",
    "court": "/court/{id}",
    "callout": "/callout/{id}",
}


def render_card(kind, record_id):
    """Возвращает PNG-байты карточки или None."""
    path = _PATHS.get(kind)
    if not path:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None

    _ensure_server()
    url = f"http://127.0.0.1:{_port}" + path.format(id=record_id)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(device_scale_factor=2)
            page.goto(url, wait_until="networkidle", timeout=15000)
            el = page.query_selector("#doc")
            png = el.screenshot() if el else None
            browser.close()
            return png
    except Exception as e:
        print(f"[card_image] рендер не удался: {e}")
        return None
