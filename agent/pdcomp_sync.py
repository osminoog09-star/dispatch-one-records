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
    # если настроек нет — создаём из шаблона, чтобы агент не остался без конфигурации
    if not os.path.exists(path):
        example = os.path.join(_base_dir(), "sync-config.example.ini")
        if os.path.exists(example):
            try:
                import shutil
                shutil.copyfile(example, path)
                print("[config] создан sync-config.ini из шаблона — впиши свои данные")
            except Exception:
                pass
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


_PROFILE = None


def fetch_profile():
    """Профиль с сайта (позывной + никнейм) по ключу агента. None если не зарегистрирован."""
    global _PROFILE
    try:
        req = urllib.request.Request(f"{SITE_URL}/api/profile", method="GET")
        req.add_header("X-Api-Key", API_KEY)
        with urllib.request.urlopen(req, timeout=10) as resp:
            _PROFILE = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _PROFILE = None
        else:
            print(f"[warn] профиль: HTTP {e.code}")
    except Exception as e:
        print(f"[warn] профиль недоступен: {e}")
    return _PROFILE


def _lspdfr_dir():
    # PDCOMP_STORE = ...\LSPDFR\pdComp\data\store → LSPDFR на 3 уровня выше
    return os.path.dirname(os.path.dirname(os.path.dirname(PDCOMP_STORE)))


def _set_ini_value(path, key, value, section=None):
    """Меняет key=value в ini (опц. внутри секции). True если что-то изменил."""
    if not os.path.exists(path):
        return False
    import re as _re
    try:
        lines = open(path, "r", encoding="utf-8-sig").read().splitlines()
    except Exception:
        return False
    out, cur, changed = [], "", False
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            cur = s[1:-1].strip().lower()
            out.append(line); continue
        m = _re.match(r"^(\s*)([A-Za-z0-9_]+)(\s*=\s*)(.*)$", line)
        if m and m.group(2).lower() == key.lower() and (section is None or cur == section.lower()):
            newline = f"{m.group(1)}{m.group(2)}{m.group(3)}{value}"
            if newline != line:
                changed = True
            out.append(newline)
        else:
            out.append(line)
    if changed:
        try:
            open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
        except Exception as e:
            print(f"[warn] не записать {os.path.basename(path)}: {e}")
            return False
    return changed


def apply_callsign_to_game(callsign, nickname):
    """Прописывает позывной/имя во все игровые конфиги — как игрок задал на сайте."""
    base = _lspdfr_dir()
    targets = [
        (os.path.join(base, "GrammarPolice", "custom.ini"), "Callsign", None),
        (os.path.join(base, "CalloutInterface.ini"), "MDTCallsign", None),
        (os.path.join(base, "BlueLineScanner.ini"), "VizLabel", None),
        (os.path.join(base, "pdComp", "config.ini"), "Callsign", "Officer"),
    ]
    changed = False
    for path, key, section in targets:
        if _set_ini_value(path, key, callsign, section):
            changed = True
    if nickname:
        _set_ini_value(os.path.join(base, "pdComp", "config.ini"), "Name", nickname, "Officer")
    if changed:
        print(f"[✓] позывной в игре обновлён на {callsign}")
    return changed


GENERIC_OFFICER = {"", "officer", "unknown", "n/a", "-"}


def _resolve_officer(raw_name, profile=None):
    """Имя офицера из игры → (позывной, имя). Обезличенное 'Officer' считаем своим."""
    prof = profile or _PROFILE or _CONFIG_PROFILE
    raw = (raw_name or "").strip()
    if raw.lower() in GENERIC_OFFICER:
        return (prof.get("callsign") or "UNKNOWN", prof.get("nickname") or raw or "UNKNOWN")
    if prof.get("nickname") and raw.lower() == prof["nickname"].strip().lower():
        return (prof.get("callsign") or raw, raw)
    return (raw, raw)          # чужой офицер — как есть


# профиль из локального конфига (если сайт недоступен)
_CONFIG_PROFILE = {"callsign": _setting("CALLSIGN", ""), "nickname": _setting("NICKNAME", "")}


def map_arrest(a):
    callsign, officer_name = _resolve_officer(a.get("OfficerName"))
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

    # номера машин из текста ареста ("plate 82WIM168")
    import re
    narr = a.get("Narrative") or ""
    plates = re.findall(r"plate[s]?\s+([0-9A-Z]{5,8}(?:\s*,\s*[0-9A-Z]{5,8})*)", narr)
    plate_list = []
    for grp in plates:
        for p in re.split(r"\s*,\s*", grp):
            if p and p not in plate_list:
                plate_list.append(p)

    return {
        "external_id": a.get("Id"),
        "callsign": callsign,          # позывной из игры (pdComp config.ini [Officer])
        "officer_name": officer_name,  # имя персонажа
        "suspect_name": a.get("SubjectFullName") or "Неизвестный",
        "suspect_dob": a.get("SubjectDob"),
        "zone": fix_mojibake(a.get("Location")),
        "game_time": a.get("ArrestedAtWall") or a.get("ArrestedAt"),
        "charges": charges,
        "found_items": evidence,
        "vehicle_plates": plate_list,
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
    """Русское имя, а в скобках английское: 'Судья Оуэн Фелд (Hon. Owen Feld)'.
    Если имя уже английское (совпадает) — не дублируем."""
    if not ru_name:
        return ru_name
    en = _english_name(ru_name, role)
    if not en:
        return ru_name
    if en.strip().lower() == ru_name.strip().lower():
        return ru_name                      # одно и то же имя — показываем один раз
    if not any("а" <= ch.lower() <= "я" for ch in ru_name):
        return ru_name                      # имя и так на латинице
    return f"{ru_name} ({en})"


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


def map_citation(ct):
    prof = _PROFILE or {}
    charges, fine = [], 0.0
    for c in (ct.get("Lines") or ct.get("Charges") or []):
        if isinstance(c, dict):
            code = c.get("ChargeCode") or c.get("Code") or ""
            desc = c.get("Description") or ""
            charges.append(f"{code} · {desc}".strip(" ·"))
            fine += float(c.get("Fine") or 0)
        else:
            charges.append(str(c))
    callsign, officer = _resolve_officer(ct.get("OfficerName"))
    return {
        "external_id": ct.get("Id"),
        "callsign": callsign,
        "officer_name": officer,
        "subject_name": ct.get("SubjectFullName") or ct.get("Subject") or "Неизвестный",
        "issued_at": ct.get("IssuedAtWall") or ct.get("IssuedAt") or ct.get("CreatedAt"),
        "location": fix_mojibake(ct.get("Location")),
        "charges": charges,
        "fine": int(round(fine)),
        "notes": ct.get("Narrative") or ct.get("Notes"),
    }


def map_warning(w):
    callsign, officer = _resolve_officer(w.get("OfficerName"))
    return {
        "external_id": w.get("Id"),
        "callsign": callsign,
        "officer_name": officer,
        "subject_name": w.get("SubjectFullName") or "Неизвестный",
        "issued_at": w.get("IssuedAtWall") or w.get("IssuedAt"),
        "location": fix_mojibake(w.get("Location")),
        "reason": w.get("Reason"),
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


# ---------- Живые данные из плагина DispatchOne.MDT (mdt.jsonl) ----------
def mdt_file():
    """Путь к mdt.jsonl, куда пишет игровой плагин (проверки ped/plate, статус смены)."""
    return os.path.join(_lspdfr_dir(), "DispatchOne", "mdt.jsonl")


def read_mdt():
    """Читает mdt.jsonl построчно. Возвращает список записей (dict) с type ped/plate/duty."""
    path = mdt_file()
    if not os.path.exists(path):
        return []
    out = []
    try:
        for line in open(path, "r", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if isinstance(rec, dict) and rec.get("type"):
                    out.append(rec)
            except Exception:
                continue
    except Exception as e:
        print(f"[warn] не прочитать mdt.jsonl: {e}")
    return out


def map_ped_check(r):
    """Проверка человека из плагина → документ NPC для сайта."""
    prof = _PROFILE or _CONFIG_PROFILE
    first = (r.get("first") or "").strip()
    last = (r.get("last") or "").strip()
    name = (first + " " + last).strip() or "Неизвестный"
    return {
        "external_id": "ped:" + name.lower() + ":" + (r.get("ts") or ""),
        "name": name,
        "dob": r.get("dob"),
        "male": bool(r.get("male")),
        "wanted": bool(r.get("wanted")),
        "license": r.get("license"),
        "citations": int(r.get("citations") or 0),
        "advisory": r.get("advisory"),
        "callsign": prof.get("callsign") or "UNKNOWN",
        "seen_at": r.get("ts"),
    }


def map_plate_check(r):
    """Проверка машины из плагина → запись транспорта для сайта."""
    prof = _PROFILE or _CONFIG_PROFILE
    return {
        "external_id": "plate:" + (r.get("plate") or "") + ":" + (r.get("ts") or ""),
        "plate": (r.get("plate") or "").strip(),
        "make": r.get("make"),
        "model": r.get("model"),
        "color": r.get("color"),
        "vclass": r.get("class"),
        "owner": r.get("owner"),
        "insurance": r.get("insurance"),
        "registration": r.get("registration"),
        "callsign": prof.get("callsign") or "UNKNOWN",
        "seen_at": r.get("ts"),
    }


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


GAME_PROCESSES = ["GTA5.exe", "GTA5_Enhanced.exe", "RAGEPluginHook.exe",
                  "RAGEPluginHook64.exe", "PlayGTAV.exe"]

# режим владельца сайта: публикуем сами, сервер не нужен
OWNER_MODE = _setting("AUTO_PUBLISH", "0") in ("1", "true", "yes", "on")


def is_game_running():
    """Игра/RagePluginHook запущены?"""
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=0x08000000)  # без окна консоли
        low = (out.stdout or "").lower()
        return any(p.lower() in low for p in GAME_PROCESSES)
    except Exception:
        return False


def auto_publish():
    """После выхода из игры — опубликовать данные на сайт (если включено)."""
    if _setting("AUTO_PUBLISH", "0") not in ("1", "true", "yes", "on"):
        return
    import subprocess
    root = os.path.dirname(_base_dir())          # ...\AIDispatcher
    script = os.path.join(root, "publish.py")
    if not os.path.exists(script):
        return
    print("[publish] публикую данные на сайт...")
    try:
        r = subprocess.run(["py", script], cwd=root, capture_output=True,
                           text=True, timeout=600, creationflags=0x08000000)
        tail = [l for l in (r.stdout or "").splitlines() if l.strip()][-2:]
        for l in tail:
            print("   " + l)
    except Exception as e:
        print(f"[publish] не удалось: {e}")


def _via_gateway(payload):
    """Отправка через шлюз Cloudflare (токен не в клиенте). (ok, msg)."""
    url = _setting("GATEWAY_URL", "")
    key = _setting("GATEWAY_KEY", "")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Client-Key", key)
    req.add_header("User-Agent", "lapd-agent")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.load(r)
            return bool(resp.get("ok")), resp.get("msg", "принято")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:160]
        return False, f"шлюз {e.code}: {detail}"
    except Exception as e:
        return False, f"нет связи со шлюзом: {e}"


def _gh_upload_records(repo, token, profile, arrests, citations, cases, shifts=None, warnings=None,
                       ped_checks=None, plate_checks=None, duty_events=None):
    """Кладёт данные игрока в inbox. Через шлюз (если задан GATEWAY_URL) или прямо в GitHub."""
    import base64
    payload = {"profile": profile, "arrests": arrests or [],
               "citations": citations or [], "cases": cases or [],
               "shifts": shifts or [], "warnings": warnings or [],
               "ped_checks": ped_checks or [], "plate_checks": plate_checks or [],
               "duty_events": duty_events or [],
               "sent_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if not any(payload[k] for k in ("arrests", "citations", "cases", "shifts", "warnings",
                                     "ped_checks", "plate_checks", "duty_events")):
        return True, "новых данных нет"

    # приоритет — шлюз (токена в клиенте нет)
    if _setting("GATEWAY_URL", ""):
        return _via_gateway(payload)

    if not repo or not token:
        return False, "не заданы репозиторий/ключ"
    safe = "".join(ch for ch in (profile.get("callsign") or "unknown")
                   if ch.isalnum() or ch in "-_")
    path = f"server/inbox/{safe}-{int(time.time())}.json"
    content = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")).decode("ascii")
    body = json.dumps({"message": f"Данные офицера {profile.get('callsign')}",
                       "content": content}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/contents/{path}", data=body, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "dispatch-one-agent")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status in (200, 201):
                return True, (f"отправлено ({len(payload['arrests'])} задерж., "
                              f"{len(payload['citations'])} штраф., {len(payload['cases'])} суд.)")
            return False, f"GitHub вернул {r.status}"
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:160]
        if e.code == 401:
            return False, "неверный ключ доступа (401) — обратись к руководству"
        if e.code == 404:
            return False, "репозиторий не найден или нет доступа (404)"
        return False, f"GitHub {e.code}: {detail}"
    except Exception as e:
        return False, f"нет связи с GitHub: {e}"


def upload_to_github(shift=None):
    """Игрок: отправить свои записи прямо в GitHub (без хостинга)."""
    if _setting("UPLOAD_MODE", "").lower() != "github":
        return

    profile = {
        "callsign": _setting("CALLSIGN", ""),
        "nickname": _setting("NICKNAME", ""),
        "discord": _setting("DISCORD", ""),
    }
    if not profile["callsign"]:
        print("[github] не задан позывной в настройках")
        return

    mine = (profile["nickname"] or "").strip().lower()
    generic = {"", "officer", "unknown"}

    def ours(rec):
        nm = (rec.get("OfficerName") or "").strip().lower()
        return nm in generic or (mine and nm == mine)

    arrests = [a for a in (read_json(os.path.join(PDCOMP_STORE, "arrests.json")) or []) if ours(a)]
    cits = [c for c in (read_json(os.path.join(PDCOMP_STORE, "citations.json")) or []) if ours(c)]
    warns = [w for w in (read_json(os.path.join(PDCOMP_STORE, "warnings.json")) or []) if ours(w)]
    warns = [map_warning(w) for w in warns]
    our_ids = {r.get("Id") for r in arrests + cits if r.get("Id")}
    cases = [c for c in (read_json(os.path.join(PDCOMP_STORE, "cases.json")) or [])
             if (c.get("CitationId") or c.get("ArrestReportId")) in our_ids]

    # живые данные из плагина (проверки ped/plate, статус смены)
    ped_checks, plate_checks, duty_events = [], [], []
    for rec in read_mdt():
        t = rec.get("type")
        if t == "ped":
            ped_checks.append(map_ped_check(rec))
        elif t == "plate":
            plate_checks.append(map_plate_check(rec))
        elif t == "duty":
            duty_events.append({"on_duty": rec.get("onDuty"), "at": rec.get("ts"),
                                "external_id": "duty:" + str(rec.get("ts"))})

    print("[github] отправляю данные...")
    ok, msg = _gh_upload_records(
        _setting("GITHUB_REPO", ""), _setting("GITHUB_TOKEN", ""),
        profile, arrests, cits, cases, [shift] if shift else [], warns,
        ped_checks, plate_checks, duty_events)
    print(("[github] " if ok else "[github] ошибка: ") + msg)


def _save_owner_shift(shift):
    """Владелец: смена в очередь pending_shifts.json (publish.py её заберёт)."""
    root = os.path.dirname(_base_dir())
    path = os.path.join(root, "pending_shifts.json")
    try:
        queue = []
        if os.path.exists(path):
            queue = json.load(open(path, encoding="utf-8"))
        queue.append(shift)
        json.dump(queue, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception as e:
        print(f"[shift] не сохранена: {e}")


def _count_records():
    """Сколько всего арестов и штрафов сейчас в pdComp (для замера смены)."""
    arrests = len(read_json(os.path.join(PDCOMP_STORE, "arrests.json")) or [])
    cits = read_json(os.path.join(PDCOMP_STORE, "citations.json")) or []
    fines = sum(sum(float(l.get("Fine") or 0) for l in (c.get("Lines") or [])) for c in cits)
    return arrests, len(cits), int(round(fines))


def build_shift(started_ts, baseline):
    """Собирает запись смены: длительность и что сделано за сессию."""
    prof = _PROFILE or _CONFIG_PROFILE
    a0, c0, f0 = baseline
    a1, c1, f1 = _count_records()
    dur_min = max(0, int((time.time() - started_ts) / 60))
    hour = time.localtime(started_ts).tm_hour
    stype = "day" if 6 <= hour < 18 else ("evening" if 18 <= hour < 23 else "night")
    return {
        "callsign": prof.get("callsign") or "UNKNOWN",
        "officer_name": prof.get("nickname") or "",
        "shift_type": stype,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started_ts)),
        "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_min": dur_min,
        "arrests": max(0, a1 - a0),
        "traffic_stops": max(0, c1 - c0),   # штрафы ≈ остановки транспорта
        "fines_total": max(0, f1 - f0),
    }


def watch_game():
    """Режим ожидания игры: спим, пока игра не запущена; синхронизируем во время игры;
    после выхода из игры — публикуем на сайт."""
    print("Режим автозапуска: жду запуска игры...")
    was_running = False
    seen = {}
    shift_start = None
    shift_base = (0, 0, 0)
    while True:
        try:
            running = is_game_running()

            if running and not was_running:
                print("Игра запущена — слежу за данными.")
                seen = {}
                shift_start = time.time()
                shift_base = _count_records()   # замер на начало смены
                # профиль: с сайта, а если владелец/сайт недоступен — из локального конфига
                prof = None if OWNER_MODE else fetch_profile()
                if not prof:
                    prof = _CONFIG_PROFILE
                if prof.get("callsign"):
                    apply_callsign_to_game(prof["callsign"], prof.get("nickname"))

            # В режиме владельца (AUTO_PUBLISH) сервер не нужен: publish.py читает
            # игровые файлы напрямую. Не долбим сеть и не сыпем ошибками.
            if running and not OWNER_MODE:
                for fname, fn in (("arrests.json", sync_arrests),
                                  ("cases.json", sync_court)):
                    path = os.path.join(PDCOMP_STORE, fname)
                    mtime = os.path.getmtime(path) if os.path.exists(path) else 0
                    if mtime != seen.get(fname):
                        a, b = fn()
                        if a:
                            print(f"    {fname}: новых {a}")
                        seen[fname] = mtime

            if was_running and not running:
                print("Игра закрыта.")
                shift = None
                if shift_start:
                    shift = build_shift(shift_start, shift_base)
                    if shift["duration_min"] >= 1:
                        print(f"    смена: {shift['duration_min']} мин, "
                              f"задержаний {shift['arrests']}, штрафов {shift['traffic_stops']}")
                    else:
                        shift = None   # слишком короткая — не считаем
                shift_start = None
                if shift and OWNER_MODE:
                    _save_owner_shift(shift)   # владелец: смена в очередь для publish
                upload_to_github(shift)        # игрок: отправка данных в GitHub
                auto_publish()                 # владелец: сборка и публикация сайта
                print("Жду следующего запуска игры...")

            was_running = running
            time.sleep(POLL_SECONDS if running else 20)
        except KeyboardInterrupt:
            print("\nВыход.")
            break
        except Exception as e:
            print(f"[err] цикл: {e}")
            time.sleep(20)


def main():
    if _setting("WATCH_GAME", "1") in ("1", "true", "yes", "on"):
        print("Dispatch One sync-агент запущен.")
        print(f"  pdComp store: {PDCOMP_STORE}")
        print(f"  сайт: {SITE_URL}\n")
        watch_game()
        return

    print(f"Dispatch One sync-агент запущен.")
    print(f"  pdComp store: {PDCOMP_STORE}")
    print(f"  сайт: {SITE_URL}")
    print(f"  опрос каждые {POLL_SECONDS} сек. Ctrl+C для выхода.\n")

    seen = {}
    while True:
        try:
            # позывной/имя — с сайта (регистрация игрока) → прописать в игру
            prof = fetch_profile()
            if prof and prof.get("callsign"):
                apply_callsign_to_game(prof["callsign"], prof.get("nickname"))
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
