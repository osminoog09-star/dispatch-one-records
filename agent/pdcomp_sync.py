"""
Dispatch One — sync-агент.
Читает данные pdComp (JSON-файлы, куда игра пишет аресты/дела/штрафы) и шлёт на сайт.
Никаких выдуманных данных — только то, что реально произошло в игре.

Запуск (рядом с игрой):  python pdcomp_sync.py
"""
import os
import json
import time

import requests

# ---------- Настройки ----------
PDCOMP_STORE = os.environ.get(
    "PDCOMP_STORE",
    r"C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy\plugins\LSPDFR\pdComp\data\store",
)
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")
API_KEY = os.environ.get("RECORDS_API_KEY", "dev-key")
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "8"))


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
        "judge": cc.get("JudgeName"),
        "prosecutor": cc.get("ProsecutorName"),
        "defense": cc.get("DefenseCounsel"),
        "courtroom": cc.get("Courtroom"),
        "plea": cc.get("Plea"),
        "appeal_filed": cc.get("AppealFiled"),
        "charges": cc.get("ChargeDispositions") or [],
        "timeline": cc.get("Timeline") or [],
    }


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
            r = requests.post(f"{SITE_URL}/api/case", json=payload,
                              headers={"X-Api-Key": API_KEY}, timeout=10)
            if r.status_code == 201:
                new += 1
                print(f"[+] арест: {payload['suspect_name']} ({payload['officer_name']})")
            elif r.status_code == 200 and r.json().get("duplicate"):
                dup += 1
            else:
                print(f"[warn] сервер вернул {r.status_code}: {r.text[:120]}")
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
            r = requests.post(f"{SITE_URL}/api/court", json=payload,
                              headers={"X-Api-Key": API_KEY}, timeout=10)
            if r.status_code == 201:
                new += 1
                print(f"[+] суд.дело: {payload['subject_name']}")
            elif r.status_code == 200:
                upd += 1
            else:
                print(f"[warn] суд сервер вернул {r.status_code}: {r.text[:120]}")
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
