"""Слой БД (SQLite, stdlib — без ORM). Дела, офицеры, история статусов."""
import sqlite3
import datetime
from contextlib import contextmanager

import config

# Статусы дела (конечный автомат) + русские подписи
STATUSES = ["submitted", "under_review", "in_court", "convicted", "dismissed", "closed"]
STATUS_RU = {
    "submitted": "Подано",
    "under_review": "На рассмотрении",
    "in_court": "В суде",
    "convicted": "Приговор",
    "dismissed": "Отклонено",
    "closed": "Закрыто",
}
LICENSE_RU = {
    "Valid": "Действительны",
    "Suspended": "Приостановлены",
    "Expired": "Просрочены",
    "Unlicensed": "Без прав",
    "None": "—",
    None: "—",
}


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
                FOREIGN KEY (officer_id) REFERENCES officers(id)
            );
            CREATE TABLE IF NOT EXISTS status_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                FOREIGN KEY (case_id) REFERENCES cases(id)
            );
            """
        )


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def get_or_create_officer(callsign, name=None):
    with get_conn() as c:
        row = c.execute("SELECT * FROM officers WHERE callsign=?", (callsign,)).fetchone()
        if row:
            if name and not row["name"]:
                c.execute("UPDATE officers SET name=? WHERE id=?", (name, row["id"]))
            return row["id"]
        cur = c.execute("INSERT INTO officers (callsign, name) VALUES (?, ?)", (callsign, name))
        return cur.lastrowid


def create_case(data):
    """data: dict от мода. Возвращает id нового дела."""
    officer_id = get_or_create_officer(data.get("callsign", "UNKNOWN"), data.get("officer_name"))
    now = _now()
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO cases
               (officer_id, suspect_name, wanted, license_state, citations, zone, postal,
                game_time, created_at, screenshot, status)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'submitted')""",
            (
                officer_id,
                data.get("suspect_name", "Неизвестный"),
                1 if data.get("wanted") else 0,
                data.get("license_state"),
                int(data.get("citations", 0) or 0),
                data.get("zone"),
                data.get("postal"),
                data.get("game_time"),
                now,
                data.get("screenshot"),
            ),
        )
        case_id = cur.lastrowid
        c.execute(
            "INSERT INTO status_log (case_id, status, changed_at) VALUES (?, 'submitted', ?)",
            (case_id, now),
        )
        return case_id


def _row_to_case(r):
    return {
        **dict(r),
        "wanted": bool(r["wanted"]),
        "status_ru": STATUS_RU.get(r["status"], r["status"]),
        "license_ru": LICENSE_RU.get(r["license_state"], r["license_state"] or "—"),
    }


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
    with get_conn() as c:
        return [dict(r) for r in c.execute(
            """SELECT officers.id, officers.callsign, officers.name,
                      COUNT(cases.id) AS cases_count,
                      SUM(CASE WHEN cases.wanted=1 THEN 1 ELSE 0 END) AS wanted_count
               FROM officers LEFT JOIN cases ON cases.officer_id = officers.id
               GROUP BY officers.id ORDER BY cases_count DESC""").fetchall()]


def get_officer(callsign):
    with get_conn() as c:
        r = c.execute("SELECT * FROM officers WHERE callsign=?", (callsign,)).fetchone()
        return dict(r) if r else None


def summary_counts():
    with get_conn() as c:
        total = c.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        today = c.execute("SELECT COUNT(*) FROM cases WHERE substr(created_at,1,10)=?",
                          (datetime.date.today().isoformat(),)).fetchone()[0]
        officers = c.execute("SELECT COUNT(*) FROM officers").fetchone()[0]
        return {"total": total, "today": today, "officers": officers}
