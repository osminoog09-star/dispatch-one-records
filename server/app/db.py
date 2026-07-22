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
    "is_test": "INTEGER",
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
        c.execute("INSERT INTO status_log (case_id, status, changed_at) VALUES (?, 'submitted', ?)",
                  (case_id, now))
        return case_id


def _jsonlist(val):
    if not val:
        return []
    try:
        return json.loads(val)
    except Exception:
        return [x.strip() for x in str(val).split(",") if x.strip()]


def _row_to_case(r):
    d = dict(r)
    d["wanted"] = bool(r["wanted"])
    d["status_ru"] = STATUS_RU.get(r["status"], r["status"])
    d["license_ru"] = LICENSE_RU.get(r["license_state"], r["license_state"] or "—")
    d["charges"] = _jsonlist(r["charges"]) if "charges" in r.keys() else []
    d["found_items"] = _jsonlist(r["found_items"]) if "found_items" in r.keys() else []
    d["created_fmt"] = fmt_dt(r["created_at"])
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
