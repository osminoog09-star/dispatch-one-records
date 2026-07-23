"""
Dispatch One — sync-агент.
Читает данные pdComp (JSON-файлы, куда игра пишет аресты/дела/штрафы) и шлёт на сайт.
Никаких выдуманных данных — только то, что реально произошло в игре.

Запуск (рядом с игрой):  python pdcomp_sync.py
"""
import os
import json
import time
import urllib.request
import urllib.error

# ---------- Настройки ----------
import sys


def _base_dir():
    # рядом с .exe (PyInstaller) или рядом со скриптом
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _load_config_file():
    """Читает sync-config.ini рядом с программой (key=value). Возвращает dict."""
    cfg = {}
    path = os.path.join(_base_dir(), "sync-config.ini")
    if os.path.exists(path):
        try:
            for line in open(path, "r", encoding="utf-8-sig"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith(";") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip().upper()] = v.strip()
        except Exception as e:
            print(f"[warn] не прочитать sync-config.ini: {e}")
    return cfg


_FILE = _load_config_file()


def _setting(key, default):
    return _FILE.get(key) or os.environ.get(key) or default


PDCOMP_STORE = _setting(
    "PDCOMP_STORE",
    r"C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy\plugins\LSPDFR\pdComp\data\store",
)
SITE_URL = _setting("SITE_URL", "http://localhost:8000").rstrip("/")
API_KEY = _setting("RECORDS_API_KEY", "dev-key")
POLL_SECONDS = int(_setting("POLL_SECONDS", "8"))


def fix_mojibake(s):
    """Чинит адреса, побитые двойной кодировкой (UTF-8, прочитанный как CP1251).
    Корректный русский текст при этом не трогается (там decode падает и остаётся оригинал)."""
    if not s:
        return s
    try:
        return s.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def map_arrest(a):
    charges = []
    for c in a.get("Charges", []):
        code = c.get("ChargeCode", "")
        desc = c.get("Description", "")
        cls = c.get("LegalClass")
        line = f"{code} · {desc}".strip(" ·")
        if cls:
            line += f" ({cls})"
        charges.append(line)

    evidence = [e.get("Description", "") for e in a.get("Evidence", []) if e.get("Description")]

    officer = a.get("OfficerName") or "UNKNOWN"
    return {
        "external_id": a.get("Id"),
        "callsign": officer,          # pdComp хранит имя офицера; используем как ключ
        "officer_name": officer,
        "suspect_name": a.get("SubjectFullName") or "Неизвестный",
        "zone": fix_mojibake(a.get("Location")),
        "game_time": a.get("ArrestedAtWall") or a.get("ArrestedAt"),
        "charges": charges,
        "found_items": evidence,
        "notes": a.get("Narrative"),
        "is_test": False,             # это реальные данные из игры
    }


import difflib

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
# титулы уже в ЛАТИНИЦЕ (сравнение идёт после транслитерации)
_TITLE_WORDS = {"sudya", "zam", "gor", "prokurora", "prokuror", "pom", "rezervnyy",
                "zashchitnik", "gorodskogo", "pomoshchnik", "zamestitel",
                "hon", "dda", "ada", "the", "public", "defender", "counsel"}


def _translit(s):
    return "".join(_TRANSLIT.get(ch, _TRANSLIT.get(ch.lower(), ch)) for ch in (s or ""))


def _name_key(s):
    """Ключ для сравнения: транслит, убраны титулы и пунктуация."""
    latin = _translit(s or "").lower()
    toks = [t for t in latin.replace(".", " ").replace(",", " ").split()
            if t and t not in _TITLE_WORDS]
    return " ".join(toks)


def _load_personnel():
    path = os.path.join(os.path.dirname(PDCOMP_STORE), "court_personnel.json")
    pools = {"judges": [], "prosecutors": [], "defenseCounsel": []}
    data = read_json(path)
    if isinstance(data, dict):
        for role in pools:
            for p in data.get(role, []):
                nm = p.get("name")
                if nm:
                    pools[role].append((nm, _name_key(nm)))
    return pools


_PERSONNEL = None


def _personnel():
    global _PERSONNEL
    if _PERSONNEL is None:
        _PERSONNEL = _load_personnel()
    return _PERSONNEL


def _english_name(ru_name, role):
    """Английское имя из court_personnel по русскому (фаззи-матч). None если не найдено."""
    if not ru_name:
        return None
    pool = _personnel().get(role, [])
    best, best_r = None, 0.0
    key = _name_key(ru_name)
    for en, en_key in pool:
        r = difflib.SequenceMatcher(None, key, en_key).ratio()
        if r > best_r:
            best_r, best = r, en
    return best if (best and best_r >= 0.5) else None


def _bilingual(ru_name, role):
    """Русское имя, а в скобках английское: 'Судья Оуэн Фелд (Hon. Owen Feld)'."""
    if not ru_name:
        return ru_name
    en = _english_name(ru_name, role)
    return f"{ru_name} ({en})" if en else ru_name


def map_court_case(cc):
    return {
        "external_id": cc.get("Id"),
        "subject_name": cc.get("SubjectFullName") or "Неизвестный",
        "source": "Арест" if cc.get("ArrestReportId") else ("Штраф" if cc.get("CitationId") else "—"),
        "filed_at": cc.get("FiledAt"),
        "status": cc.get("Status"),
        "outcome": cc.get("Outcome"),
        "sentence": cc.get("Sentence"),
        "notes": cc.get("Notes"),
        "judge": _bilingual(cc.get("JudgeName"), "judges"),
        "prosecutor": _bilingual(cc.get("ProsecutorName"), "prosecutors"),
        "defense": _bilingual(cc.get("DefenseCounsel"), "defenseCounsel"),
        "courtroom": cc.get("Courtroom"),
        "plea": cc.get("Plea"),
        "appeal_filed": cc.get("AppealFiled"),
        "charges": cc.get("ChargeDispositions") or [],
        "timeline": cc.get("Timeline") or [],
    }


def post_json(url, payload, api_key):
    """POST JSON через стандартную библиотеку (без внешних зависимостей).
    Возвращает (status_code, body_dict)."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("X-Api-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8")
            return resp.status, (json.loads(data) if data else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "ignore")[:200]}


def read_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[warn] не прочитать {os.path.basename(path)}: {e}")
        return None


def sync_arrests():
    path = os.path.join(PDCOMP_STORE, "arrests.json")
    arrests = read_json(path)
    if arrests is None:
        return 0, 0
    new, dup = 0, 0
    for a in arrests:
        payload = map_arrest(a)
        try:
            status, body = post_json(f"{SITE_URL}/api/case", payload, API_KEY)
            if status == 201:
                new += 1
                print(f"[+] арест: {payload['suspect_name']} ({payload['officer_name']})")
            elif status == 200 and body.get("duplicate"):
                dup += 1
            else:
                print(f"[warn] сервер вернул {status}: {body}")
        except Exception as e:
            print(f"[err] отправка не удалась: {e}")
    return new, dup


def sync_court():
    path = os.path.join(PDCOMP_STORE, "cases.json")
    cases = read_json(path)
    if cases is None:
        return 0, 0
    new, upd = 0, 0
    for cc in cases:
        payload = map_court_case(cc)
        try:
            status, body = post_json(f"{SITE_URL}/api/court", payload, API_KEY)
            if status == 201:
                new += 1
                print(f"[+] суд.дело: {payload['subject_name']}")
            elif status == 200:
                upd += 1
            else:
                print(f"[warn] суд сервер вернул {status}: {body}")
        except Exception as e:
            print(f"[err] суд отправка: {e}")
    return new, upd


def main():
    print(f"Dispatch One sync-агент запущен.")
    print(f"  pdComp store: {PDCOMP_STORE}")
    print(f"  сайт: {SITE_URL}")
    print(f"  опрос каждые {POLL_SECONDS} сек. Ctrl+C для выхода.\n")

    seen = {}
    while True:
        try:
            for fname, fn in (("arrests.json", sync_arrests), ("cases.json", sync_court)):
                path = os.path.join(PDCOMP_STORE, fname)
                mtime = os.path.getmtime(path) if os.path.exists(path) else 0
                if mtime != seen.get(fname):
                    a, b = fn()
                    if a:
                        print(f"    {fname}: новых {a}, обновлено/дублей {b}")
                    seen[fname] = mtime
        except KeyboardInterrupt:
            print("\nВыход.")
            break
        except Exception as e:
            print(f"[err] цикл: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
