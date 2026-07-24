"""Слой БД (SQLite, stdlib — без ORM). Дела, офицеры, история статусов."""
import sqlite3
import json
import datetime
from contextlib import contextmanager

import config

STATUSES = ["submitted", "under_review", "in_court", "convicted", "dismissed", "closed"]
STATUS_RU = {
    "submitted": "Подано", "under_review": "На рассмотрении", "in_court": "В суде",
    "convicted": "Приговор", "dismissed": "Отклонено", "closed": "Закрыто",
}
LICENSE_RU = {
    "Valid": "Действительны", "Suspended": "Приостановлены", "Expired": "Просрочены",
    "Unlicensed": "Без прав", "None": "—", None: "—",
}

# Доп. колонки (для миграции существующей БД)
EXTRA_COLUMNS = {
    "vehicle_model": "TEXT", "vehicle_plate": "TEXT", "vehicle_color": "TEXT",
    "charges": "TEXT", "found_items": "TEXT", "reason": "TEXT", "notes": "TEXT",
    "mugshot": "TEXT", "fine": "INTEGER", "bail": "INTEGER", "jail_time": "TEXT",
    "is_test": "INTEGER", "external_id": "TEXT",
}


def fmt_dt(iso):
    """ISO → 'ДД.ММ.ГГГГ ЧЧ:ММ' (реальное время задержания)."""
    try:
        dt = datetime.datetime.fromisoformat(iso)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso or "—"


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS officers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                callsign TEXT UNIQUE NOT NULL,
                name TEXT
            );
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                officer_id INTEGER NOT NULL,
                suspect_name TEXT,
                wanted INTEGER DEFAULT 0,
                license_state TEXT,
                citations INTEGER DEFAULT 0,
                zone TEXT,
                postal TEXT,
                game_time TEXT,
                created_at TEXT NOT NULL,
                screenshot TEXT,
                status TEXT NOT NULL DEFAULT 'submitted',
                discord_sent INTEGER DEFAULT 0,
                vehicle_model TEXT, vehicle_plate TEXT, vehicle_color TEXT,
                charges TEXT, found_items TEXT, reason TEXT, notes TEXT,
                mugshot TEXT, fine INTEGER, bail INTEGER, jail_time TEXT,
                is_test INTEGER DEFAULT 0,
                FOREIGN KEY (officer_id) REFERENCES officers(id)
            );
            CREATE TABLE IF NOT EXISTS status_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                FOREIGN KEY (case_id) REFERENCES cases(id)
            );
            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                officer_id INTEGER NOT NULL,
                shift_type TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_min INTEGER DEFAULT 0,
                arrests INTEGER DEFAULT 0,
                traffic_stops INTEGER DEFAULT 0,
                pursuits INTEGER DEFAULT 0,
                pit INTEGER DEFAULT 0,
                callouts INTEGER DEFAULT 0,
                fines_total INTEGER DEFAULT 0,
                is_test INTEGER DEFAULT 0,
                FOREIGN KEY (officer_id) REFERENCES officers(id)
            );
            """
        )
        # миграция cases
        existing = {r["name"] for r in c.execute("PRAGMA table_info(cases)").fetchall()}
        for col, typ in EXTRA_COLUMNS.items():
            if col not in existing:
                c.execute(f"ALTER TABLE cases ADD COLUMN {col} {typ}")
        # миграция officers (статус доступности)
        oexisting = {r["name"] for r in c.execute("PRAGMA table_info(officers)").fetchall()}
        for col, typ in {"current_status": "TEXT", "status_since": "TEXT"}.items():
            if col not in oexisting:
                c.execute(f"ALTER TABLE officers ADD COLUMN {col} {typ}")
        c.execute(
            """CREATE TABLE IF NOT EXISTS status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                officer_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                changed_at TEXT NOT NULL
            )""")
        c.execute(
            """CREATE TABLE IF NOT EXISTS profiles (
                token TEXT PRIMARY KEY,
                callsign TEXT,
                nickname TEXT,
                discord TEXT,
                updated_at TEXT
            )""")
        c.execute(
            """CREATE TABLE IF NOT EXISTS court_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                subject_name TEXT,
                source TEXT,
                filed_at TEXT,
                status INTEGER,
                outcome INTEGER,
                sentence TEXT,
                notes TEXT,
                judge TEXT, prosecutor TEXT, defense TEXT, courtroom TEXT, plea TEXT,
                appeal_filed INTEGER DEFAULT 0,
                charges TEXT, timeline TEXT,
                synced_at TEXT
            )""")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------- Авто-вывод статей из данных (то, чего игра сама не даёт) ----------
def derive_charges(data):
    """Формирует список статей по тому, что известно об аресте."""
    charges = []
    if data.get("wanted"):
        charges.append("Нахождение в розыске")
    lic = data.get("license_state")
    if lic == "Suspended":
        charges.append("Управление ТС с приостановленными правами")
    elif lic == "Expired":
        charges.append("Управление с просроченными правами")
    elif lic == "Unlicensed":
        charges.append("Управление ТС без прав")
    for item in (data.get("found_items") or []):
        low = str(item).lower()
        if any(w in low for w in ["оруж", "пистол", "ствол", "нож"]):
            charges.append("Незаконное хранение оружия")
        elif any(w in low for w in ["наркот", "марих", "кокаин", "вещест"]):
            charges.append("Хранение запрещённых веществ")
        elif any(w in low for w in ["краден", "угон"]):
            charges.append("Хранение краденого имущества")
    if (data.get("citations") or 0) >= 3:
        charges.append("Множественные нарушения ПДД")
    # убрать дубли, сохранить порядок
    seen, out = set(), []
    for ch in charges:
        if ch not in seen:
            seen.add(ch); out.append(ch)
    return out


def get_or_create_officer(callsign, name=None):
    with get_conn() as c:
        row = c.execute("SELECT * FROM officers WHERE callsign=?", (callsign,)).fetchone()
        if row:
            # обновляем имя, если мод прислал актуальное (имя персонажа могло смениться)
            if name and name != row["name"]:
                c.execute("UPDATE officers SET name=? WHERE id=?", (name, row["id"]))
            return row["id"]
        cur = c.execute("INSERT INTO officers (callsign, name) VALUES (?, ?)", (callsign, name))
        return cur.lastrowid


def create_case(data):
    officer_id = get_or_create_officer(data.get("callsign", "UNKNOWN"), data.get("officer_name"))
    now = _now()

    found = data.get("found_items") or []
    if isinstance(found, str):
        found = [x.strip() for x in found.split(",") if x.strip()]

    charges = data.get("charges")
    if not charges:                       # статей нет — выводим автоматически
        charges = derive_charges({**data, "found_items": found})
    elif isinstance(charges, str):
        charges = [x.strip() for x in charges.split(",") if x.strip()]

    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO cases
               (officer_id, suspect_name, wanted, license_state, citations, zone, postal,
                game_time, created_at, screenshot, status,
                vehicle_model, vehicle_plate, vehicle_color, charges, found_items, reason, notes,
                mugshot, fine, bail, jail_time, is_test)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'submitted', ?,?,?,?,?,?,?, ?,?,?,?, ?)""",
            (
                officer_id, data.get("suspect_name", "Неизвестный"),
                1 if data.get("wanted") else 0, data.get("license_state"),
                int(data.get("citations", 0) or 0), data.get("zone"), data.get("postal"),
                data.get("game_time"), now, data.get("screenshot"),
                data.get("vehicle_model"), data.get("vehicle_plate"), data.get("vehicle_color"),
                json.dumps(charges, ensure_ascii=False), json.dumps(found, ensure_ascii=False),
                data.get("reason"), data.get("notes"),
                data.get("mugshot"),
                int(data["fine"]) if data.get("fine") not in (None, "") else None,
                int(data["bail"]) if data.get("bail") not in (None, "") else None,
                data.get("jail_time"),
                1 if data.get("is_test") else 0,
            ),
        )
        case_id = cur.lastrowid
        if data.get("external_id"):
            c.execute("UPDATE cases SET external_id=? WHERE id=?", (data["external_id"], case_id))
        c.execute("INSERT INTO status_log (case_id, status, changed_at) VALUES (?, 'submitted', ?)",
                  (case_id, now))
        return case_id


def case_exists_external(external_id):
    if not external_id:
        return None
    with get_conn() as c:
        r = c.execute("SELECT id FROM cases WHERE external_id=?", (external_id,)).fetchone()
        return r["id"] if r else None


def _jsonlist(val):
    if not val:
        return []
    try:
        return json.loads(val)
    except Exception:
        return [x.strip() for x in str(val).split(",") if x.strip()]


def _parse_charge(s):
    """'PC.1320 · Неявка в суд (Проступок)' → {code, desc, cls}."""
    import re as _re
    m = _re.match(r"^\s*(\S+)\s·\s(.+?)(?:\s\(([^)]+)\))?\s*$", s or "")
    if m:
        return {"code": m.group(1), "desc": m.group(2), "cls": m.group(3) or ""}
    return {"code": "", "desc": s or "", "cls": ""}


def _row_to_case(r):
    d = dict(r)
    d["wanted"] = bool(r["wanted"])
    d["status_ru"] = STATUS_RU.get(r["status"], r["status"])
    d["license_ru"] = LICENSE_RU.get(r["license_state"], r["license_state"] or "—")
    d["charges"] = [localize(x) for x in (_jsonlist(r["charges"]) if "charges" in r.keys() else [])]
    d["charges_parsed"] = [_parse_charge(x) for x in d["charges"]]
    d["found_items"] = _jsonlist(r["found_items"]) if "found_items" in r.keys() else []
    d["notes"] = localize_narrative(d.get("notes"))
    d["created_fmt"] = fmt_dt(r["created_at"])
    ext = r["external_id"] if "external_id" in r.keys() and r["external_id"] else str(r["id"])
    try:
        num = int(ext.replace("-", "")[:8], 16) % 90000000 + 10000000
    except Exception:
        num = 10000000 + (r["id"] or 0)
    d["arrest_no"] = f"AR-{num}"
    d["is_test"] = bool(r["is_test"]) if "is_test" in r.keys() else False
    return d


def list_cases(limit=100, officer_id=None, status=None):
    q = """SELECT cases.*, officers.callsign, officers.name AS officer_name
           FROM cases JOIN officers ON officers.id = cases.officer_id"""
    conds, params = [], []
    if officer_id:
        conds.append("cases.officer_id=?"); params.append(officer_id)
    if status:
        conds.append("cases.status=?"); params.append(status)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY cases.id DESC LIMIT ?"; params.append(limit)
    with get_conn() as c:
        return [_row_to_case(r) for r in c.execute(q, params).fetchall()]


def get_case(case_id):
    with get_conn() as c:
        r = c.execute(
            """SELECT cases.*, officers.callsign, officers.name AS officer_name
               FROM cases JOIN officers ON officers.id = cases.officer_id
               WHERE cases.id=?""", (case_id,)).fetchone()
        if not r:
            return None
        case = _row_to_case(r)
        case["history"] = [dict(h) for h in c.execute(
            "SELECT status, changed_at FROM status_log WHERE case_id=? ORDER BY id", (case_id,)).fetchall()]
        for h in case["history"]:
            h["status_ru"] = STATUS_RU.get(h["status"], h["status"])
        return case


def set_status(case_id, status):
    if status not in STATUSES:
        return False
    with get_conn() as c:
        c.execute("UPDATE cases SET status=? WHERE id=?", (status, case_id))
        c.execute("INSERT INTO status_log (case_id, status, changed_at) VALUES (?,?,?)",
                  (case_id, status, _now()))
    return True


def mark_discord_sent(case_id):
    with get_conn() as c:
        c.execute("UPDATE cases SET discord_sent=1 WHERE id=?", (case_id,))


def list_officers_with_stats():
    # Статистика ЧЕСТНАЯ — тестовые дела (is_test=1) в подсчёт не идут.
    with get_conn() as c:
        rows = c.execute(
            """SELECT officers.id, officers.callsign, officers.name, officers.current_status,
                      COUNT(cases.id) AS cases_count,
                      SUM(CASE WHEN cases.wanted=1 THEN 1 ELSE 0 END) AS wanted_count
               FROM officers
               LEFT JOIN cases ON cases.officer_id = officers.id AND cases.is_test=0
               GROUP BY officers.id ORDER BY cases_count DESC""").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            si = status_info(d.get("current_status"))
            d["status_ru"], d["status_cls"] = si["ru"], si["cls"]
            out.append(d)
        return out


# Статусы доступности офицера (мод шлёт при смене в игре)
DUTY_STATUS = {
    "10-8": {"ru": "На службе", "cls": "on"},
    "10-6": {"ru": "Занят", "cls": "busy"},
    "10-23": {"ru": "На вызове", "cls": "scene"},
    "10-7": {"ru": "Не на службе", "cls": "off"},
}


def status_info(code):
    return DUTY_STATUS.get(code, {"ru": "Не на службе", "cls": "off"})


def set_officer_status(callsign, status, name=None):
    officer_id = get_or_create_officer(callsign, name)
    now = _now()
    with get_conn() as c:
        c.execute("UPDATE officers SET current_status=?, status_since=? WHERE id=?",
                  (status, now, officer_id))
        c.execute("INSERT INTO status_history (officer_id, status, changed_at) VALUES (?,?,?)",
                  (officer_id, status, now))
    return officer_id


def get_officer(callsign):
    with get_conn() as c:
        r = c.execute("SELECT * FROM officers WHERE callsign=?", (callsign,)).fetchone()
        if not r:
            return None
        d = dict(r)
        si = status_info(d.get("current_status"))
        d["status_ru"], d["status_cls"] = si["ru"], si["cls"]
        d["status_since_fmt"] = fmt_dt(d["status_since"]) if d.get("status_since") else None
        d["status_log"] = [
            {"status": h["status"], "status_ru": status_info(h["status"])["ru"],
             "cls": status_info(h["status"])["cls"], "at": fmt_dt(h["changed_at"])}
            for h in c.execute(
                "SELECT status, changed_at FROM status_history WHERE officer_id=? ORDER BY id DESC LIMIT 30",
                (r["id"],)).fetchall()
        ]
        return d


# ---------- Локализация (pdComp местами отдаёт англ. шаблоны) ----------
import re

_TIMELINE_TITLE = {
    "Case filed": "Дело заведено",
    "Hearing scheduled": "Слушание назначено",
    "Hearing held": "Слушание проведено",
    "Plea entered": "Заявление стороны",
    "Disposition entered": "Вынесено решение",
    "Probation ordered": "Назначен испытательный срок",
    "Bench warrant issued": "Выдан ордер на арест",
    "Appeal filed": "Подана апелляция",
}
# фразы — от длинных к коротким (порядок важен)
_PHRASES = [
    ("The defendant was found not responsible on this line.", "По этому пункту вина не установлена."),
    ("The citation was heard and resolved in favor of the defendant.", "Дело по штрафу решено в пользу защиты."),
    ("The court accepted this line and assessed the applicable fine. Appearance was required for the hearing.",
     "Суд принял этот пункт и назначил штраф. Явка на слушание была обязательна."),
    ("Responsibility was found on the filed citation; the fine order is now active.",
     "По штрафу установлена ответственность; постановление о штрафе действует."),
    ("No sentence (case notguilty)", "Без наказания (не виновен)"),
    ("mandatory appearance tracked", "обязательная явка учтена"),
    ("case file opened", "дело заведено"),
    ("assigned before", "назначен перед"),
    ("heard the matter in", "рассмотрел дело в"),
    ("No fine assessed", "Штраф не назначен"),
    ("No sentence", "Без наказания"),
    ("Not responsible", "Не признаёт вину"),
    ("Not guilty", "Не виновен"),
    ("NotGuilty", "Не виновен"),
    ("Responsible", "Признаёт вину"),
    ("Convicted", "Осуждён"),
    ("Dismissed", "Дело прекращено"),
    ("Guilty", "Виновен"),
    ("State v.", "Штат против"),
    ("court costs", "судебные издержки"),
    ("costs", "издержки"),
    ("incl.", "вкл."),
    ("Fine", "Штраф"),
    ("Infraction", "Нарушение"),
    ("Misdemeanor", "Проступок"),
    ("Felony", "Тяжкое"),
]
# кириллические заглавные → латинские двойники (для номеров залов/отделов)
_CYR2LAT = {"А": "A", "Б": "B", "В": "B", "Г": "G", "Д": "D", "Е": "E", "Ж": "J", "З": "Z",
            "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P",
            "Р": "R", "С": "C", "Т": "T", "У": "U", "Ф": "F", "Х": "H", "Ц": "C", "Ч": "C"}


def _fix_rooms(s):
    """Буква номера зала/отдела после цифры → латиница: '24Г' → '24G'."""
    return re.sub(r"(\d)([А-Я])", lambda m: m.group(1) + _CYR2LAT.get(m.group(2), m.group(2)), s)


def localize(text):
    if not text or not isinstance(text, str):
        return text
    out = text
    for en, ru in _PHRASES:
        out = out.replace(en, ru)
    return _fix_rooms(out)


_MONTHS = {"Jan": "января", "Feb": "февраля", "Mar": "марта", "Apr": "апреля",
           "May": "мая", "Jun": "июня", "Jul": "июля", "Aug": "августа",
           "Sep": "сентября", "Oct": "октября", "Nov": "ноября", "Dec": "декабря"}


def localize_narrative(text):
    """Перевод сгенерированного pdComp описания ареста на русский (имена не трогаем)."""
    if not text or not isinstance(text, str):
        return text
    t = text
    for en, ru in [
        ("After investigation, probable cause was determined for the arrest.",
         "После разбирательства установлено достаточное основание для ареста."),
        ("following a", "по вызову"),
        ("Officer arrested", "сотрудник задержал"),
        ("(DOB ", "(дата рожд. "),
    ]:
        t = t.replace(en, ru)
    t = t.replace(" call.", ".").replace(" call,", ",").replace(" call ", " ")
    t = re.sub(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\b",
               lambda m: m.group(2) + " " + _MONTHS[m.group(1)], t)
    if t.startswith("On "):
        t = t[3:]
    return t


# ---------- Судебный реестр (из pdComp cases.json) ----------
COURT_OUTCOME = {0: "В ожидании", 1: "Дело прекращено", 2: "Не виновен", 3: "Осуждён"}
COURT_OUTCOME_CLS = {0: "st-submitted", 1: "st-dismissed", 2: "st-dismissed", 3: "st-convicted"}


def court_label(status, outcome, appeal):
    if appeal:
        return "Апелляция", "st-in_court"
    if status != 3:
        return "В ожидании", "st-submitted"
    return COURT_OUTCOME.get(outcome, "Закрыто"), COURT_OUTCOME_CLS.get(outcome, "st-closed")


def upsert_court_case(data):
    ext = data.get("external_id")
    now = _now()
    charges = json.dumps(data.get("charges") or [], ensure_ascii=False)
    timeline = json.dumps(data.get("timeline") or [], ensure_ascii=False)
    with get_conn() as c:
        existing = c.execute("SELECT id FROM court_cases WHERE external_id=?", (ext,)).fetchone() if ext else None
        row = (data.get("subject_name"), data.get("source"), data.get("filed_at"),
               data.get("status"), data.get("outcome"), data.get("sentence"), data.get("notes"),
               data.get("judge"), data.get("prosecutor"), data.get("defense"),
               data.get("courtroom"), data.get("plea"), 1 if data.get("appeal_filed") else 0,
               charges, timeline, now)
        if existing:
            c.execute("""UPDATE court_cases SET subject_name=?, source=?, filed_at=?, status=?,
                         outcome=?, sentence=?, notes=?, judge=?, prosecutor=?, defense=?,
                         courtroom=?, plea=?, appeal_filed=?, charges=?, timeline=?, synced_at=?
                         WHERE id=?""", row + (existing["id"],))
            return existing["id"], False
        cur = c.execute("""INSERT INTO court_cases
            (subject_name, source, filed_at, status, outcome, sentence, notes, judge, prosecutor,
             defense, courtroom, plea, appeal_filed, charges, timeline, synced_at, external_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row + (ext,))
        return cur.lastrowid, True


def _row_to_court(r):
    d = dict(r)
    lbl, cls = court_label(r["status"], r["outcome"], r["appeal_filed"])
    d["label"], d["label_cls"] = lbl, cls

    charges = _jsonlist(r["charges"]) if "charges" in r.keys() else []
    for ch in charges:
        ch["Sentence"] = localize(ch.get("Sentence"))
        ch["CourtNote"] = localize(ch.get("CourtNote"))
        ch["Severity"] = localize(ch.get("Severity"))
    d["charges"] = charges

    timeline = _jsonlist(r["timeline"]) if "timeline" in r.keys() else []
    for t in timeline:
        t["Title"] = _TIMELINE_TITLE.get(t.get("Title"), localize(t.get("Title")))
        t["Detail"] = localize(t.get("Detail"))
    d["timeline"] = timeline

    d["sentence"] = localize(d.get("sentence"))
    d["plea"] = localize(d.get("plea"))
    d["notes"] = localize(d.get("notes"))
    d["courtroom"] = _fix_rooms(d["courtroom"]) if d.get("courtroom") else d.get("courtroom")
    d["filed_fmt"] = fmt_dt(r["filed_at"]) if r["filed_at"] else "—"
    # номер дела (детерминированный из ID)
    ext = r["external_id"] or str(r["id"])
    try:
        num = int(ext.replace("-", "")[:8], 16) % 9000000 + 1000000
    except Exception:
        num = 1000000 + (r["id"] or 0)
    d["case_no"] = f"CA-CR-{num}"
    return d


def list_court_cases(limit=200):
    with get_conn() as c:
        return [_row_to_court(r) for r in c.execute(
            "SELECT * FROM court_cases ORDER BY filed_at DESC LIMIT ?", (limit,)).fetchall()]


def get_court_case(cid):
    with get_conn() as c:
        r = c.execute("SELECT * FROM court_cases WHERE id=?", (cid,)).fetchone()
        return _row_to_court(r) if r else None


def new_token():
    import secrets
    return secrets.token_hex(8)


def register_profile(token, callsign, nickname, discord=None):
    with get_conn() as c:
        exists = c.execute("SELECT token FROM profiles WHERE token=?", (token,)).fetchone()
        if exists:
            c.execute("UPDATE profiles SET callsign=?, nickname=?, discord=?, updated_at=? WHERE token=?",
                      (callsign, nickname, discord, _now(), token))
        else:
            c.execute("INSERT INTO profiles (token, callsign, nickname, discord, updated_at) VALUES (?,?,?,?,?)",
                      (token, callsign, nickname, discord, _now()))
    get_or_create_officer(callsign, nickname)


def get_profile(token):
    with get_conn() as c:
        r = c.execute("SELECT * FROM profiles WHERE token=?", (token,)).fetchone()
        return dict(r) if r else None


def court_summary():
    with get_conn() as c:
        total = c.execute("SELECT COUNT(*) FROM court_cases").fetchone()[0]
        pending = c.execute("SELECT COUNT(*) FROM court_cases WHERE status!=3").fetchone()[0]
        closed = c.execute("SELECT COUNT(*) FROM court_cases WHERE status=3").fetchone()[0]
        appeals = c.execute("SELECT COUNT(*) FROM court_cases WHERE appeal_filed=1").fetchone()[0]
        return {"total": total, "pending": pending, "closed": closed, "appeals": appeals}


def summary_counts():
    # Только реальные дела (тесты исключены — статистика честная).
    with get_conn() as c:
        total = c.execute("SELECT COUNT(*) FROM cases WHERE is_test=0").fetchone()[0]
        today = c.execute("SELECT COUNT(*) FROM cases WHERE is_test=0 AND substr(created_at,1,10)=?",
                          (datetime.date.today().isoformat(),)).fetchone()[0]
        officers = c.execute("SELECT COUNT(*) FROM officers").fetchone()[0]
        tests = c.execute("SELECT COUNT(*) FROM cases WHERE is_test=1").fetchone()[0]
        return {"total": total, "today": today, "officers": officers, "tests": tests}


def delete_test_cases():
    with get_conn() as c:
        ids = [row[0] for row in c.execute("SELECT id FROM cases WHERE is_test=1").fetchall()]
        if ids:
            qmarks = ",".join("?" * len(ids))
            c.execute(f"DELETE FROM status_log WHERE case_id IN ({qmarks})", ids)
            c.execute("DELETE FROM cases WHERE is_test=1")
        n2 = c.execute("SELECT COUNT(*) FROM shifts WHERE is_test=1").fetchone()[0]
        c.execute("DELETE FROM shifts WHERE is_test=1")
        return len(ids) + n2


# ---------- Смены (рапорт смены) ----------
SHIFT_TYPE_RU = {"day": "дневная", "evening": "вечерняя", "night": "ночная", None: "—"}


def create_shift(data):
    officer_id = get_or_create_officer(data.get("callsign", "UNKNOWN"), data.get("officer_name"))
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO shifts
               (officer_id, shift_type, started_at, ended_at, duration_min,
                arrests, traffic_stops, pursuits, pit, callouts, fines_total, is_test)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                officer_id, data.get("shift_type"),
                data.get("started_at") or _now(), data.get("ended_at") or _now(),
                int(data.get("duration_min", 0) or 0),
                int(data.get("arrests", 0) or 0), int(data.get("traffic_stops", 0) or 0),
                int(data.get("pursuits", 0) or 0), int(data.get("pit", 0) or 0),
                int(data.get("callouts", 0) or 0), int(data.get("fines_total", 0) or 0),
                1 if data.get("is_test") else 0,
            ),
        )
        return cur.lastrowid


def _row_to_shift(r):
    d = dict(r)
    d["is_test"] = bool(r["is_test"]) if "is_test" in r.keys() else False
    d["type_ru"] = SHIFT_TYPE_RU.get(r["shift_type"], r["shift_type"] or "—")
    dm = r["duration_min"] or 0
    d["duration_h"] = f"{dm // 60}ч {dm % 60}м"
    d["started_fmt"] = fmt_dt(r["started_at"])
    return d


def list_shifts(limit=100, officer_id=None):
    q = """SELECT shifts.*, officers.callsign, officers.name AS officer_name
           FROM shifts JOIN officers ON officers.id = shifts.officer_id"""
    params = []
    if officer_id:
        q += " WHERE shifts.officer_id=?"; params.append(officer_id)
    q += " ORDER BY shifts.id DESC LIMIT ?"; params.append(limit)
    with get_conn() as c:
        return [_row_to_shift(r) for r in c.execute(q, params).fetchall()]


def get_shift(shift_id):
    with get_conn() as c:
        r = c.execute(
            """SELECT shifts.*, officers.callsign, officers.name AS officer_name
               FROM shifts JOIN officers ON officers.id = shifts.officer_id
               WHERE shifts.id=?""", (shift_id,)).fetchone()
        return _row_to_shift(r) if r else None
