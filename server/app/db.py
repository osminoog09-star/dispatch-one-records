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
    "is_test": "INTEGER", "external_id": "TEXT", "suspect_dob": "TEXT",
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
        # миграция officers (статус доступности, звание, отдел, discord)
        oexisting = {r["name"] for r in c.execute("PRAGMA table_info(officers)").fetchall()}
        for col, typ in {"current_status": "TEXT", "status_since": "TEXT",
                         "rank": "TEXT", "department": "TEXT", "discord": "TEXT",
                         "is_admin": "INTEGER"}.items():
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
            """CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate TEXT,
                suspect_name TEXT,
                officer_id INTEGER,
                zone TEXT,
                seen_at TEXT,
                source_ext TEXT,
                UNIQUE(plate, source_ext)
            )""")
        # миграция vehicles: данные из проверки номера плагином (марка/модель/цвет/владелец…)
        _vcols = {r["name"] for r in c.execute("PRAGMA table_info(vehicles)").fetchall()}
        for col, typ in {"make": "TEXT", "model": "TEXT", "color": "TEXT",
                         "vclass": "TEXT", "owner": "TEXT", "insurance": "TEXT",
                         "registration": "TEXT"}.items():
            if col not in _vcols:
                c.execute(f"ALTER TABLE vehicles ADD COLUMN {col} {typ}")
        # документы NPC из проверок личности (плагин OnPedCheck)
        c.execute(
            """CREATE TABLE IF NOT EXISTS ped_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                dob TEXT,
                male INTEGER,
                wanted INTEGER,
                license TEXT,
                citations INTEGER DEFAULT 0,
                advisory TEXT,
                officer_id INTEGER,
                seen_at TEXT,
                source_ext TEXT UNIQUE
            )""")
        # события смены от диспетчера (плагин OnDutyStateChanged)
        c.execute(
            """CREATE TABLE IF NOT EXISTS duty_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                on_duty INTEGER,
                at TEXT,
                officer_id INTEGER,
                source_ext TEXT UNIQUE
            )""")
        # миграция shifts: source_ext для дедупа смен из duty-событий
        _scols = {r["name"] for r in c.execute("PRAGMA table_info(shifts)").fetchall()}
        if "source_ext" not in _scols:
            c.execute("ALTER TABLE shifts ADD COLUMN source_ext TEXT")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_shifts_src "
                  "ON shifts(source_ext) WHERE source_ext IS NOT NULL")
        c.execute(
            """CREATE TABLE IF NOT EXISTS callouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                officer_id INTEGER,
                callout_type TEXT,
                priority TEXT,
                location TEXT,
                zone TEXT,
                description TEXT,
                outcome TEXT,
                occurred_at TEXT,
                suspect_name TEXT
            )""")
        # миграция callouts (для старых баз)
        _cocols = {r["name"] for r in c.execute("PRAGMA table_info(callouts)").fetchall()}
        if "suspect_name" not in _cocols:
            c.execute("ALTER TABLE callouts ADD COLUMN suspect_name TEXT")
        c.execute(
            """CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                officer_id INTEGER,
                subject_name TEXT,
                issued_at TEXT,
                location TEXT,
                reason TEXT
            )""")
        c.execute(
            """CREATE TABLE IF NOT EXISTS citations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                officer_id INTEGER,
                subject_name TEXT,
                issued_at TEXT,
                location TEXT,
                charges TEXT,
                fine INTEGER DEFAULT 0,
                notes TEXT
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
        if data.get("suspect_dob"):
            c.execute("UPDATE cases SET suspect_dob=? WHERE id=?", (data["suspect_dob"], case_id))
        c.execute("INSERT INTO status_log (case_id, status, changed_at) VALUES (?, 'submitted', ?)",
                  (case_id, now))
        # машины из ареста → в реестр транспорта
        for plate in (data.get("vehicle_plates") or []):
            try:
                c.execute("""INSERT OR IGNORE INTO vehicles (plate, suspect_name, officer_id, zone, seen_at, source_ext)
                             VALUES (?,?,?,?,?,?)""",
                          (plate, data.get("suspect_name"), officer_id, data.get("zone"),
                           data.get("game_time") or now, data.get("external_id") or str(case_id)))
            except Exception:
                pass
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
    d["zone"] = localize_narrative(d.get("zone"))
    d["notes"] = localize_narrative(d.get("notes"))
    d["created_fmt"] = fmt_dt(r["created_at"])
    d["game_time_fmt"] = fmt_dt(r["game_time"]) if r["game_time"] else None
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
            h["changed_fmt"] = fmt_dt(h["changed_at"])
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
        # Личный состав = только зарегистрированные офицеры (есть профиль).
        # Имена из игровых записей (чужие штрафы/аресты) в состав не попадают.
        rows = c.execute(
            """SELECT officers.id, officers.callsign, officers.name, officers.current_status,
                      officers.rank, officers.department, officers.discord, officers.is_admin,
                      COUNT(cases.id) AS cases_count,
                      SUM(CASE WHEN cases.wanted=1 THEN 1 ELSE 0 END) AS wanted_count
               FROM officers
               LEFT JOIN cases ON cases.officer_id = officers.id AND cases.is_test=0
               WHERE officers.callsign IN (SELECT callsign FROM profiles)
               GROUP BY officers.id ORDER BY cases_count DESC, officers.callsign""").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            si = status_info(d.get("current_status"))
            d["status_ru"], d["status_cls"] = si["ru"], si["cls"]
            d["rank_label"] = staff_label(d.get("rank"))
            d["department_label"] = staff_label(d.get("department"))
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
        d["rank_label"] = staff_label(d.get("rank"))
        d["department_label"] = staff_label(d.get("department"))
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
    "Appeal resolved": "Апелляция рассмотрена",
}
# фразы — от длинных к коротким (порядок важен)
_PHRASES = [
    ("The court accepted this line and assessed the applicable fine. Appearance was required for the hearing.",
     "Суд принял этот пункт и назначил штраф. Явка на слушание была обязательна."),
    ("Responsibility was found on this citation line. Correction eligibility remains noted for fine handling.",
     "Ответственность по пункту установлена. Возможность исправления отмечена для расчёта штрафа."),
    ("Full payment received by the court clerk; the hearing was vacated.",
     "Судебный секретарь получил полную оплату; слушание отменено."),
    ("Paid without contest before the hearing date.",
     "Оплачено без оспаривания до даты слушания."),
    ("Officer testimony / citation record / Fix-It / correction status",
     "Показания офицера / запись штрафа / исправимое нарушение / статус исправления"),
    ("The citation line was sustained and the listed fine was entered.",
     "Пункт штрафа подтверждён, указанная сумма внесена."),
    ("The court sustained the citation and entered the listed fines.",
     "Суд подтвердил штраф и внёс указанные суммы."),
    ("The citation was upheld at hearing and costs were assessed.",
     "Штраф подтверждён на слушании, издержки назначены."),
    ("The court closed this citation line without a fine.",
     "Суд закрыл этот пункт без штрафа."),
    ("No separate supporting evidence was submitted for this count.",
     "Отдельные подтверждающие материалы по этому пункту не представлены."),
    ("This count was sustained after hearing.",
     "Пункт подтверждён после слушания."),
    ("Probation terms: obey laws, report as directed, submit to searches when required.",
     "Условия испытательного срока: соблюдать законы, являться по требованию, проходить проверки при необходимости."),
    ("Probation terms: obey laws, report as directed",
     "Условия испытательного срока: соблюдать законы, являться по требованию"),
    ("Failure to pay court-ordered citation fines",
     "Неуплата назначенных судом штрафов"),
    ("Appeal denied; original disposition affirmed.",
     "Апелляция отклонена; исходное решение оставлено в силе."),
    ("Defense filed notice of appeal.",
     "Защита подала уведомление об апелляции."),
    ("Motion to dismiss granted", "Ходатайство о прекращении удовлетворено"),
    ("Defense appeal denied", "Апелляция защиты отклонена"),
    ("No contest (fine paid)", "Без оспаривания (штраф оплачен)"),
    ("Probation grant:", "Испытательный срок:"),
    ("United States v.", "США против"),
    ("The defendant was found not responsible on this line.", "По этому пункту вина не установлена."),
    ("The citation was heard and resolved in favor of the defendant.", "Дело по штрафу решено в пользу защиты."),
    ("Responsibility was found on the filed citation; the fine order is now active.",
     "По штрафу установлена ответственность; постановление о штрафе действует."),
    ("Alternate Public Defender", "альтернативный общественный защитник"),
    ("Private Counsel", "частный защитник"),
    ("Self-Represented", "самостоятельная защита"),
    ("Public Defender", "общественный защитник"),
    ("Deputy City Attorney", "заместитель городского прокурора"),
    ("City Attorney", "городской прокурор"),
    ("Traffic Commissioner", "комиссар по дорожным делам"),
    ("Motion to dismiss", "ходатайство о прекращении"),
    ("Failure to pay", "неуплата"),
    ("No contest", "без оспаривания"),
    ("Fine paid", "штраф оплачен"),
    ("Fix-It", "исправимое нарушение"),
    ("fine reduced", "штраф снижен"),
    ("license suspension review", "пересмотр приостановки прав"),
    ("appeal denied", "апелляция отклонена"),
    ("affirmed", "решение оставлено в силе"),
    ("felony probation", "испытательный срок по тяжкому делу"),
    ("Not Guilty", "Не виновен"),
    ("Not виновен", "Не виновен"),
    ("not guilty", "не виновен"),
    ("guilty", "виновен"),
    ("No sentence (case notguilty)", "Без наказания (не виновен)"),
    ("mandatory appearance tracked", "обязательная явка учтена"),
    ("case file opened", "дело заведено"),
    ("assigned before", "назначен перед"),
    ("heard the matter in", "рассмотрел дело в"),
    ("No fine assessed", "Штраф не назначен"),
    ("No sentence", "Без наказания"),
    ("Court-Appointed Counsel", "назначенный защитник"),
    ("CJA Panel Counsel", "назначенная защита"),
    ("Courtroom", "зал"),
    ("Hon.", "судья"),
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
    ("Wobbler", "по усмотрению суда"),
    ("Infraction", "Нарушение"),
    ("Misdemeanor", "Проступок"),
    ("Felony", "Тяжкое"),
    # --- приговоры и предписания суда ---
    ("state prison", "тюрьма штата"),
    ("county jail", "окружная тюрьма"),
    ("traffic school or community service ordered",
     "предписаны курсы ПДД или общественные работы"),
    ("traffic school or community service", "курсы ПДД или общественные работы"),
    ("license suspended", "права приостановлены"),
    ("license revoked", "права аннулированы"),
    ("DUI program ordered", "предписана программа для пьяных водителей"),
    ("DUI program", "программа для пьяных водителей"),
    ("ignition interlock ordered", "предписан алкозамок в машину"),
    ("ignition interlock", "алкозамок"),
    ("probation ordered", "назначен испытательный срок"),
    ("probation", "испытательный срок"),
    ("community service", "общественные работы"),
    ("restitution ordered", "предписано возмещение ущерба"),
    ("restitution", "возмещение ущерба"),
    ("counseling ordered", "предписаны консультации"),
    ("weapons prohibition ordered", "назначен запрет на владение оружием"),
    ("weapons prohibition", "запрет на владение оружием"),
    ("proof-of-correction eligible", "допускается подтверждение устранения нарушения"),
    ("mandatory appearance tracked", "обязательная явка учтена"),
    ("mandatory appearance", "обязательная явка"),
    ("(strike prior)", "(с учётом прежней судимости)"),
    ("(concurrent)", "(одновременно)"),
    ("(consecutive)", "(последовательно)"),
    ("consecutive", "последовательно"),
    ("concurrent", "одновременно"),
    ("stayed PC 654", "приостановлено по статье PC 654"),
    ("suspended sentence", "условный срок"),
    ("time served", "срок отбыт"),
    (" months", " мес."),
    (" month", " мес."),
    (" years", " года"),
    (" year", " год"),
    (" days jail", " дн. тюрьмы"),
    (" day jail", " дн. тюрьмы"),
    (" days", " дн."),
    (" day", " дн."),
    ("jail", "тюрьма"),
    ("prison", "тюрьма"),
    ("ordered", "предписано"),
    ("No sentence assessed", "Наказание не назначено"),
    ("No sentence (dismissed)", "Дело прекращено"),
    ("No sentence", "Без наказания"),
    ("(dismissed)", "(прекращено)"),
    ("dismissed", "прекращено"),
    ("incl.", "вкл."),
    ("court costs", "судебные издержки"),
    ("Fine", "Штраф"),
]
# кириллические заглавные → латинские двойники (для номеров залов/отделов)
_CYR2LAT = {"А": "A", "Б": "B", "В": "B", "Г": "G", "Д": "D", "Е": "E", "Ж": "J", "З": "Z",
            "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P",
            "Р": "R", "С": "C", "Т": "T", "У": "U", "Ф": "F", "Х": "H", "Ц": "C", "Ч": "C"}

_MOJI_TO_CYR = {}
for _ch in "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя":
    try:
        _MOJI_TO_CYR[_ch.encode("utf-8").decode("cp1251")] = _ch
    except UnicodeDecodeError:
        pass


def _replace_mojibake_pairs(s):
    for bad, good in sorted(_MOJI_TO_CYR.items(), key=lambda x: len(x[0]), reverse=True):
        s = s.replace(bad, good)
    return s


def _fix_rooms(s):
    """Буква номера зала/отдела после цифры → латиница: '24Г' → '24G'."""
    return re.sub(r"(\d)([А-Я])", lambda m: m.group(1) + _CYR2LAT.get(m.group(2), m.group(2)), s)


def _cp1251_bytes(s):
    """Обратно в байты для текста, побитого чтением UTF-8 как CP1251.

    Обычный s.encode('cp1251') падает на символах, которых нет в таблице (например
    U+0098 из «И» = D0 98) — тогда адреса вроде «Р‘СѓР»СЊРІР°СЂ РРЅРЅРѕСЃРµРЅСЃ»
    оставались битыми. Такие символы возвращаем как одиночный байт.
    """
    out = bytearray()
    for ch in s:
        try:
            out += ch.encode("cp1251")
        except UnicodeEncodeError:
            code = ord(ch)
            if code < 256:
                out.append(code)
            else:
                raise
    return bytes(out)


def _fix_mojibake(s):
    """Repair UTF-8 text that was accidentally decoded as CP1251."""
    if not s or not isinstance(s, str):
        return s
    try:
        fixed = _cp1251_bytes(s).decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError, ValueError):
        fixed = s
    else:
        return fixed if re.search(r"[А-Яа-яЁё]", fixed) else s

    def repl(m):
        chunk = m.group(0)
        if not re.search(r"[ЉЊЂЃІЌљњђѓіќ№°]", chunk):
            return chunk
        try:
            return chunk.encode("cp1251").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return chunk

    return _replace_mojibake_pairs(re.sub(r"[\u0400-\u04ff\u00a0\u2116°-]+", repl, s))


def _ru_days(n):
    n = int(n)
    if n % 10 == 1 and n % 100 != 11:
        word = "день"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = "дня"
    else:
        word = "дней"
    return f"{n} {word} лишения свободы"


def localize(text):
    if not text or not isinstance(text, str):
        return text
    out = _fix_mojibake(text)
    for en, ru in _PHRASES:
        out = out.replace(en, ru)
    out = re.sub(r"\b1 года\b", "1 год", out)
    out = re.sub(r"\b([2-4]) года\b", r"\1 года", out)
    out = re.sub(r"\b([5-9]|1[0-9]|[2-9][0-9]) года\b", r"\1 лет", out)
    out = re.sub(r"\b1 год тюрьма\b", "1 год тюрьмы", out)
    out = re.sub(r"\b([0-9]+) года тюрьма\b", r"\1 года тюрьмы", out)
    out = re.sub(r"\b([0-9]+) лет тюрьма\b", r"\1 лет тюрьмы", out)
    out = out.replace(" + ", "; ")
    out = re.sub(r"\b1 год тюрьмы\b", "1 год лишения свободы", out)
    out = re.sub(r"\b([2-4]) года тюрьмы\b", r"\1 года лишения свободы", out)
    out = re.sub(r"\b([5-9]|1[0-9]|[2-9][0-9]) лет тюрьмы\b", r"\1 лет лишения свободы", out)
    out = re.sub(r"\b([0-9]+) дн\. тюрьмы\b", lambda m: _ru_days(m.group(1)), out)
    out = re.sub(r";\s*1 год последовательно\b", "; дополнительно 1 год последовательно", out)
    out = re.sub(r";\s*([2-4]) года последовательно\b", r"; дополнительно \1 года последовательно", out)
    out = re.sub(r";\s*([5-9]|1[0-9]|[2-9][0-9]) лет последовательно\b", r"; дополнительно \1 лет последовательно", out)
    out = out.replace("Виновен plea", "Признание вины")
    out = out.replace("Не виновен plea", "Заявление о невиновности")
    out = out.replace("Признание вины entered", "Внесено признание вины")
    out = out.replace("Заявление о невиновности entered", "Внесено заявление о невиновности")
    out = out.replace("plea", "заявление")
    out = out.replace(" entered", "")
    out = out.replace("; ;", ";")
    return _fix_rooms(out)


_MONTHS = {"Jan": "января", "Feb": "февраля", "Mar": "марта", "Apr": "апреля",
           "May": "мая", "Jun": "июня", "Jul": "июля", "Aug": "августа",
           "Sep": "сентября", "Oct": "октября", "Nov": "ноября", "Dec": "декабря"}


def localize_narrative(text):
    """Перевод сгенерированного pdComp описания ареста на русский (имена не трогаем)."""
    if not text or not isinstance(text, str):
        return text
    t = _fix_mojibake(text)
    for en, ru in [
        ("After investigation, probable cause was determined for the arrest.",
         "После разбирательства установлено достаточное основание для ареста."),
        ("following a", "по вызову"),
        ("Officer arrested", "сотрудник задержал"),
        ("(DOB ", "(дата рожд. "),
        ("[VH]", "[вызов]"),
        ("Subway Disturbance", "Нарушение порядка в метро"),
        ("Los Santos International", "Международный аэропорт Лос-Сантоса"),
        ("vehicle contact", "проверка транспорта"),
        ("vehicle plates", "номера ТС"),
        ("vehicle plate", "номер ТС"),
        ("involving", "с участием"),
    ]:
        t = t.replace(en, ru)
    t = t.replace(" arrested ", " задержал ")
    t = t.replace(" at ", " по адресу ")
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
        ch["LegalClass"] = localize(ch.get("LegalClass"))
        # не показывать одно и то же дважды: «Проступок · Проступок»
        if ch.get("LegalClass") and ch.get("Severity") and \
           ch["LegalClass"].strip().lower() == ch["Severity"].strip().lower():
            ch["Severity"] = ""
    d["charges"] = charges

    timeline = _jsonlist(r["timeline"]) if "timeline" in r.keys() else []
    for t in timeline:
        t["Title"] = _TIMELINE_TITLE.get(t.get("Title"), localize(t.get("Title")))
        t["Detail"] = localize(t.get("Detail"))
    d["timeline"] = timeline

    d["sentence"] = localize(d.get("sentence"))
    d["source"] = localize(d.get("source"))
    d["plea"] = localize(d.get("plea"))
    d["notes"] = localize(d.get("notes"))
    d["judge"] = localize(d.get("judge"))
    d["prosecutor"] = localize(d.get("prosecutor"))
    d["defense"] = localize(d.get("defense"))
    d["courtroom"] = _fix_rooms(localize(d["courtroom"])) if d.get("courtroom") else d.get("courtroom")
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


def list_related_court_cases_for_officer(officer_id, limit=100):
    """Суды по людям, которых офицер оформлял в арестах/штрафах/вызовах."""
    with get_conn() as c:
        rows = c.execute(
            """SELECT DISTINCT court_cases.*
               FROM court_cases
               WHERE subject_name IN (
                 SELECT suspect_name FROM cases WHERE officer_id=? AND suspect_name IS NOT NULL AND suspect_name!=''
                 UNION
                 SELECT subject_name FROM citations WHERE officer_id=? AND subject_name IS NOT NULL AND subject_name!=''
                 UNION
                 SELECT suspect_name FROM callouts WHERE officer_id=? AND suspect_name IS NOT NULL AND suspect_name!=''
                 UNION
                 SELECT subject_name FROM warnings WHERE officer_id=? AND subject_name IS NOT NULL AND subject_name!=''
               )
               ORDER BY filed_at DESC LIMIT ?""",
            (officer_id, officer_id, officer_id, officer_id, limit),
        ).fetchall()
        return [_row_to_court(r) for r in rows]


def get_court_case(cid):
    with get_conn() as c:
        r = c.execute("SELECT * FROM court_cases WHERE id=?", (cid,)).fetchone()
        return _row_to_court(r) if r else None


def upsert_citation(data):
    """Штраф из игры (pdComp citations.json)."""
    officer_id = get_or_create_officer(data.get("callsign", "UNKNOWN"), data.get("officer_name"))
    ext = data.get("external_id")
    charges = json.dumps(data.get("charges") or [], ensure_ascii=False)
    with get_conn() as c:
        if ext and c.execute("SELECT id FROM citations WHERE external_id=?", (ext,)).fetchone():
            return None, False
        cur = c.execute(
            """INSERT INTO citations (external_id, officer_id, subject_name, issued_at,
               location, charges, fine, notes) VALUES (?,?,?,?,?,?,?,?)""",
            (ext, officer_id, data.get("subject_name"), data.get("issued_at"),
             data.get("location"), charges, int(data.get("fine") or 0), data.get("notes")))
        return cur.lastrowid, True


def _row_to_citation(r):
    d = dict(r)
    d["charges"] = [localize(x) for x in _jsonlist(r["charges"])]
    d["issued_fmt"] = fmt_dt(r["issued_at"]) if r["issued_at"] else "—"
    return d


def list_citations(limit=200, officer_id=None):
    q = """SELECT citations.*, officers.callsign, officers.name AS officer_name
           FROM citations LEFT JOIN officers ON officers.id = citations.officer_id"""
    params = []
    if officer_id:
        q += " WHERE citations.officer_id=?"; params.append(officer_id)
    q += " ORDER BY citations.id DESC LIMIT ?"; params.append(limit)
    with get_conn() as c:
        return [_row_to_citation(r) for r in c.execute(q, params).fetchall()]


CALLOUT_PRIORITY_RU = {"1": "Приоритет 1 (срочный)", "2": "Приоритет 2", "3": "Приоритет 3",
                       "high": "Высокий", "medium": "Средний", "low": "Низкий", None: "—", "": "—"}


def create_callout(data):
    """Вызов, добавленный вручную (или из плагина)."""
    officer_id = get_or_create_officer(data.get("callsign", "UNKNOWN"), data.get("officer_name"))
    ext = data.get("external_id") or ("manual-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S%f"))
    with get_conn() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(callouts)").fetchall()}
        if "suspect_name" not in cols:
            c.execute("ALTER TABLE callouts ADD COLUMN suspect_name TEXT")
        if c.execute("SELECT id FROM callouts WHERE external_id=?", (ext,)).fetchone():
            return None, False
        cur = c.execute(
            """INSERT INTO callouts (external_id, officer_id, callout_type, priority,
               location, zone, description, outcome, occurred_at, suspect_name)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (ext, officer_id, data.get("callout_type"), data.get("priority"),
             data.get("location"), data.get("zone"), data.get("description"),
             data.get("outcome"), data.get("occurred_at") or _now(), data.get("suspect_name")))
        return cur.lastrowid, True


def _callout_type_from_case(data):
    text = data.get("reason") or data.get("notes") or ""
    if data.get("reason"):
        return data.get("reason")
    m = re.search(r"following a\s+(.+?)\s+call\b", text, flags=re.I)
    if m:
        title = m.group(1).strip()
        title = re.sub(r"^\[[^\]]+\]\s*", "", title).strip()
        return localize_narrative(title) or "Вызов"
    if re.search(r"vehicle contact", text, flags=re.I):
        return "Проверка транспорта"
    return "Задержание"


def _callout_location_from_case(data):
    text = data.get("notes") or ""
    m = re.search(r"\sat\s+(.+?)(?:\s+involving|\.\s+After|$)", text, flags=re.I)
    if m:
        return localize_narrative(m.group(1).strip())
    return localize_narrative(data.get("zone")) or data.get("zone")


def ensure_callout_for_case(data, case_id=None):
    """Create one CAD callout card for an arrest/case if it does not exist yet."""
    if data.get("is_test"):
        return None, False
    source = data.get("external_id") or (str(case_id) if case_id else None)
    if not source:
        return None, False
    suspect = data.get("suspect_name") or "Неизвестный"
    notes = localize_narrative(data.get("notes")) if data.get("notes") else ""
    payload = {
        "external_id": f"case-callout:{source}",
        "callsign": data.get("callsign") or "UNKNOWN",
        "officer_name": data.get("officer_name"),
        "callout_type": _callout_type_from_case(data),
        "priority": data.get("priority") or "2",
        "location": _callout_location_from_case(data),
        "zone": localize_narrative(data.get("zone")) if data.get("zone") else data.get("zone"),
        "description": notes or f"Вызов завершился задержанием: {suspect}.",
        "outcome": f"Задержан: {suspect}",
        "occurred_at": data.get("game_time") or data.get("created_at"),
        "suspect_name": suspect,
    }
    return create_callout(payload)


def backfill_callouts_from_cases():
    """Restore CAD callout cards for existing arrest records."""
    created = 0
    with get_conn() as c:
        rows = c.execute(
            """SELECT cases.*, officers.callsign, officers.name AS officer_name
               FROM cases LEFT JOIN officers ON officers.id = cases.officer_id
               WHERE cases.is_test=0
               ORDER BY cases.id"""
        ).fetchall()
    for r in rows:
        _, made = ensure_callout_for_case(dict(r), r["id"])
        if made:
            created += 1
    return created


def case_file(name):
    """Досье на человека: все записи (вызовы, аресты, штрафы, предупреждения, суд)
    с этим именем, собранные в одну хронологическую цепочку."""
    name = (name or "").strip()
    if not name:
        return None
    items = []

    def add(kind, rows, name_key, time_key, title_fn):
        for r in rows:
            d = dict(r)
            for key in ("zone", "location", "callout_type", "description", "notes"):
                if d.get(key):
                    d[key] = localize_narrative(d[key])
            for key in ("sentence", "source", "plea", "judge", "prosecutor", "defense", "courtroom"):
                if d.get(key):
                    d[key] = localize(d[key])
            items.append({"kind": kind, "id": d["id"], "when": d.get(time_key) or "",
                          "title": title_fn(d), "row": d})

    with get_conn() as c:
        cur = c.execute(
            """SELECT cases.*, officers.callsign, officers.name AS officer_name
               FROM cases LEFT JOIN officers ON officers.id = cases.officer_id
               WHERE cases.suspect_name=? COLLATE NOCASE""", (name,)).fetchall()
        add("arrest", cur, "suspect_name", "created_at", lambda d: "Задержание")
        cit = c.execute(
            """SELECT citations.*, officers.callsign, officers.name AS officer_name
               FROM citations LEFT JOIN officers ON officers.id = citations.officer_id
               WHERE citations.subject_name=? COLLATE NOCASE""", (name,)).fetchall()
        add("citation", cit, "subject_name", "issued_at", lambda d: f"Штраф ${d.get('fine') or 0}")
        wr = c.execute(
            """SELECT warnings.*, officers.callsign, officers.name AS officer_name
               FROM warnings LEFT JOIN officers ON officers.id = warnings.officer_id
               WHERE warnings.subject_name=? COLLATE NOCASE""", (name,)).fetchall()
        add("warning", wr, "subject_name", "issued_at", lambda d: "Предупреждение")
        # Синтетические вызовы-зеркала (ext 'case-callout:...') не показываем в личном
        # деле: они сгенерированы из ареста и дублировали бы его в хронологии.
        # На странице /callouts они остаются (там это журнал вызовов).
        co = c.execute(
            """SELECT callouts.*, officers.callsign, officers.name AS officer_name
               FROM callouts LEFT JOIN officers ON officers.id = callouts.officer_id
               WHERE callouts.suspect_name=? COLLATE NOCASE
                 AND (callouts.external_id IS NULL
                      OR callouts.external_id NOT LIKE 'case-callout:%')""", (name,)).fetchall()
        add("callout", co, "suspect_name", "occurred_at", lambda d: f"Вызов: {d.get('callout_type') or ''}")
        crt = c.execute("SELECT * FROM court_cases WHERE subject_name=? COLLATE NOCASE", (name,)).fetchall()
        add("court", crt, "subject_name", "filed_at",
            lambda d: "Суд: " + (localize(d["sentence"]) if d.get("sentence") else "рассмотрено"))

    # порядок вызова→арест→штраф→суд внутри одного времени
    order = {"callout": 0, "arrest": 1, "citation": 2, "warning": 3, "court": 4}
    items.sort(key=lambda x: (x["when"] or "", order.get(x["kind"], 9)))
    if not items:
        return None
    return {"name": name, "chain": items, "count": len(items)}


def person_info(name):
    """Досье-шапка: дата рождения, возраст, розыск, номера машин + документ NPC (плагин)."""
    with get_conn() as c:
        dob_row = c.execute("SELECT suspect_dob FROM cases WHERE suspect_name=? COLLATE NOCASE "
                            "AND suspect_dob IS NOT NULL AND suspect_dob!='' LIMIT 1", (name,)).fetchone()
        wanted = c.execute("SELECT MAX(wanted) FROM cases WHERE suspect_name=? COLLATE NOCASE",
                           (name,)).fetchone()[0]
        plates = [r["plate"] for r in c.execute(
            "SELECT DISTINCT plate FROM vehicles WHERE suspect_name=? COLLATE NOCASE", (name,)).fetchall()]
        # свежайший документ NPC из проверки личности в игре
        doc = c.execute(
            """SELECT dob, male, wanted, license, citations, advisory, seen_at
               FROM ped_documents WHERE name=? COLLATE NOCASE
               ORDER BY seen_at DESC LIMIT 1""", (name,)).fetchone()
    dob = (dob_row["suspect_dob"] if dob_row else None) or (doc["dob"] if doc else None)
    info = {"dob": dob, "age": None, "wanted": bool(wanted), "plates": plates,
            "gender": None, "license": None, "license_ru": None, "citations": None,
            "advisory": None, "checked_at": None}
    if doc:
        info["wanted"] = info["wanted"] or bool(doc["wanted"])
        info["gender"] = ("Мужской" if doc["male"] else "Женский")
        info["license"] = doc["license"]
        info["license_ru"] = LICENSE_STATE_RU.get(doc["license"], doc["license"])
        info["citations"] = doc["citations"]
        info["advisory"] = doc["advisory"]
        info["checked_at"] = fmt_dt(doc["seen_at"]) if doc["seen_at"] else None
    if dob:
        try:
            b = datetime.datetime.strptime(dob[:10], "%Y-%m-%d")
            info["age"] = int((datetime.datetime.now() - b).days / 365.25)
        except Exception:
            pass
    return info


LICENSE_STATE_RU = {"Valid": "действительны", "Suspended": "приостановлены",
                    "Expired": "просрочены", "Unlicensed": "нет прав", "None": "нет прав",
                    "Revoked": "аннулированы"}
DOC_STATUS_RU = {"Valid": "действует", "Expired": "просрочена", "None": "нет",
                 "Unknown": "неизвестно"}


def record_ped_document(rec):
    """Документ NPC из проверки личности (плагин). Дедуп по source_ext."""
    officer_id = get_or_create_officer(rec.get("callsign", "UNKNOWN"))
    with get_conn() as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO ped_documents
               (name, dob, male, wanted, license, citations, advisory, officer_id, seen_at, source_ext)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (rec.get("name"), rec.get("dob"), 1 if rec.get("male") else 0,
             1 if rec.get("wanted") else 0, rec.get("license"), int(rec.get("citations") or 0),
             rec.get("advisory"), officer_id, rec.get("seen_at"), rec.get("external_id")))
        return cur.rowcount > 0


def record_vehicle_check(rec):
    """Проверка номера (плагин) → запись/обогащение транспорта. Дедуп по (plate, source_ext)."""
    if not rec.get("plate"):
        return False
    officer_id = get_or_create_officer(rec.get("callsign", "UNKNOWN"))
    with get_conn() as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO vehicles
               (plate, suspect_name, officer_id, zone, seen_at, source_ext,
                make, model, color, vclass, owner, insurance, registration)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rec.get("plate"), rec.get("owner"), officer_id, None, rec.get("seen_at"),
             rec.get("external_id"), rec.get("make"), rec.get("model"), rec.get("color"),
             rec.get("vclass"), rec.get("owner"), rec.get("insurance"), rec.get("registration")))
        return cur.rowcount > 0


def record_duty_event(rec):
    """Событие смены (плагин). Дедуп по source_ext. True если новое."""
    officer_id = get_or_create_officer(rec.get("callsign", "UNKNOWN"))
    with get_conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO duty_events (on_duty, at, officer_id, source_ext) VALUES (?,?,?,?)",
            (1 if rec.get("on_duty") else 0, rec.get("at"), officer_id, rec.get("external_id")))
        return cur.rowcount > 0


def shifts_from_duty(callsign):
    """Собирает смены из парных событий (на смену → со смены) для позывного.
    Возвращает список dict со started_at/ended_at/duration_min. Не пишет в БД."""
    with get_conn() as c:
        oid = c.execute("SELECT id FROM officers WHERE callsign=?", (callsign,)).fetchone()
        if not oid:
            return []
        rows = c.execute("SELECT on_duty, at FROM duty_events WHERE officer_id=? ORDER BY at",
                         (oid["id"],)).fetchall()
    shifts, open_at = [], None
    for r in rows:
        if r["on_duty"] and open_at is None:
            open_at = r["at"]
        elif not r["on_duty"] and open_at is not None:
            try:
                t0 = datetime.datetime.fromisoformat(open_at)
                t1 = datetime.datetime.fromisoformat(r["at"])
                dur = max(0, int((t1 - t0).total_seconds() / 60))
            except Exception:
                dur = 0
            shifts.append({"started_at": open_at, "ended_at": r["at"], "duration_min": dur})
            open_at = None
    return shifts


def _shift_type_for(started_at):
    try:
        h = datetime.datetime.fromisoformat(started_at).hour
    except Exception:
        return None
    return "day" if 6 <= h < 18 else ("evening" if 18 <= h < 23 else "night")


def sync_duty_shifts(callsign, officer_name=None):
    """Создаёт смены из завершённых duty-пар (дедуп по source_ext). Возвращает число новых."""
    n = 0
    for s in shifts_from_duty(callsign):
        if s["duration_min"] < 1:
            continue
        src = "duty:%s:%s" % (s["started_at"], s["ended_at"])
        officer_id = get_or_create_officer(callsign, officer_name)
        with get_conn() as c:
            cur = c.execute(
                """INSERT OR IGNORE INTO shifts
                   (officer_id, shift_type, started_at, ended_at, duration_min, source_ext)
                   VALUES (?,?,?,?,?,?)""",
                (officer_id, _shift_type_for(s["started_at"]), s["started_at"],
                 s["ended_at"], s["duration_min"], src))
            n += 1 if cur.rowcount > 0 else 0
    return n


def list_vehicles(limit=300):
    with get_conn() as c:
        rows = c.execute(
            """SELECT vehicles.plate,
                      COUNT(DISTINCT vehicles.source_ext) AS incidents,
                      GROUP_CONCAT(DISTINCT vehicles.suspect_name) AS suspects,
                      MAX(vehicles.make) AS make, MAX(vehicles.model) AS model,
                      MAX(vehicles.color) AS color,
                      MAX(vehicles.seen_at) AS last_seen
               FROM vehicles WHERE plate IS NOT NULL AND plate!=''
               GROUP BY vehicles.plate ORDER BY last_seen DESC LIMIT ?""", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            mm = " ".join(x for x in (d.get("make"), d.get("model")) if x)
            d["vehicle"] = mm or None
            out.append(d)
        return out


def get_vehicle(plate):
    with get_conn() as c:
        rows = c.execute(
            """SELECT vehicles.*, officers.callsign
               FROM vehicles LEFT JOIN officers ON officers.id = vehicles.officer_id
               WHERE plate=? COLLATE NOCASE ORDER BY seen_at DESC""", (plate,)).fetchall()
        if not rows:
            return None
        events = [dict(r) for r in rows]
        for e in events:
            e["seen_fmt"] = fmt_dt(e["seen_at"]) if e.get("seen_at") else "—"
        suspects = sorted({e["suspect_name"] for e in events if e.get("suspect_name")})
        # сводка: самые свежие непустые данные проверки номера
        info = {}
        for key in ("make", "model", "color", "vclass", "owner", "insurance", "registration"):
            for e in events:                       # events отсортированы по seen_at DESC
                if e.get(key):
                    info[key] = e[key]
                    break
        info["vehicle"] = " ".join(x for x in (info.get("make"), info.get("model")) if x) or None
        info["insurance_ru"] = DOC_STATUS_RU.get(info.get("insurance"), info.get("insurance"))
        info["registration_ru"] = DOC_STATUS_RU.get(info.get("registration"), info.get("registration"))
        return {"plate": plate, "events": events, "suspects": suspects, "info": info}


def list_case_files(limit=200):
    """Люди, на которых есть дело (>=1 запись), с краткой сводкой для списка."""
    counts = {}
    with get_conn() as c:
        for tbl, col in [("cases", "suspect_name"), ("citations", "subject_name"),
                         ("warnings", "subject_name"), ("court_cases", "subject_name"),
                         ("callouts", "suspect_name")]:
            try:
                for r in c.execute(f"SELECT {col} AS n, COUNT(*) AS k FROM {tbl} "
                                   f"WHERE {col} IS NOT NULL AND {col}!='' GROUP BY {col} COLLATE NOCASE"):
                    counts[r["n"]] = counts.get(r["n"], 0) + r["k"]
            except Exception:
                pass
    out = []
    kind_ru = {"callout": "вызов", "arrest": "арест", "citation": "штраф",
               "warning": "предупреждение", "court": "суд"}
    order = {"callout": 0, "arrest": 1, "citation": 2, "warning": 3, "court": 4}
    for n, k in counts.items():
        cf = case_file(n)
        chain = cf["chain"] if cf else []
        by_kind = {key: 0 for key in order}
        for item in chain:
            by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
        latest = chain[-1] if chain else None
        out.append({
            "name": n,
            "count": k,
            "callouts": by_kind.get("callout", 0),
            "arrests": by_kind.get("arrest", 0),
            "citations": by_kind.get("citation", 0),
            "warnings": by_kind.get("warning", 0),
            "court": by_kind.get("court", 0),
            "latest": latest,
            "latest_kind_ru": kind_ru.get(latest["kind"], latest["kind"]) if latest else "—",
            "latest_when": fmt_dt(latest["when"]) if latest and latest.get("when") else "—",
            "latest_sort": latest["when"] if latest else "",
        })
    out.sort(key=lambda x: (x["latest_sort"], x["count"]), reverse=True)
    return out[:limit]


def _row_to_callout(r):
    d = dict(r)
    d["priority_ru"] = CALLOUT_PRIORITY_RU.get(r["priority"], r["priority"] or "—")
    d["occurred_fmt"] = fmt_dt(r["occurred_at"]) if r["occurred_at"] else "—"
    ext = r["external_id"] or str(r["id"])
    try:
        num = int("".join(ch for ch in ext if ch.isdigit())[:8] or "0") % 900000 + 100000
    except Exception:
        num = 100000 + (r["id"] or 0)
    d["callout_no"] = f"CAD-{num}"
    return d


# Вызовы-зеркала: CAD-карточки, созданные из задержаний (pdComp не отдаёт журнал
# вызовов). В журнале /callouts они нужны, но рядом с задержаниями дублируют их.
MIRROR_CALLOUT = "callouts.external_id IS NOT NULL AND callouts.external_id LIKE 'case-callout:%'"


def list_callouts(limit=200, officer_id=None, real_only=False):
    """real_only=True — без зеркал задержаний (чтобы не дублировать их в списках)."""
    q = """SELECT callouts.*, officers.callsign, officers.name AS officer_name
           FROM callouts LEFT JOIN officers ON officers.id = callouts.officer_id"""
    params, where = [], []
    if officer_id:
        where.append("callouts.officer_id=?"); params.append(officer_id)
    if real_only:
        where.append(f"NOT ({MIRROR_CALLOUT})")
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY callouts.id DESC LIMIT ?"; params.append(limit)
    with get_conn() as c:
        return [_row_to_callout(r) for r in c.execute(q, params).fetchall()]


def get_callout(cid):
    with get_conn() as c:
        r = c.execute(
            """SELECT callouts.*, officers.callsign, officers.name AS officer_name
               FROM callouts LEFT JOIN officers ON officers.id = callouts.officer_id
               WHERE callouts.id=?""", (cid,)).fetchone()
        return _row_to_callout(r) if r else None


def callouts_count(officer_id=None, real_only=False):
    q, params = "SELECT COUNT(*) FROM callouts", []
    where = []
    if officer_id:
        where.append("officer_id=?"); params.append(officer_id)
    if real_only:
        where.append(f"NOT ({MIRROR_CALLOUT})")
    if where:
        q += " WHERE " + " AND ".join(where)
    with get_conn() as c:
        return c.execute(q, params).fetchone()[0]


def upsert_warning(data):
    """Предупреждение из игры (pdComp warnings.json)."""
    officer_id = get_or_create_officer(data.get("callsign", "UNKNOWN"), data.get("officer_name"))
    ext = data.get("external_id")
    with get_conn() as c:
        if ext and c.execute("SELECT id FROM warnings WHERE external_id=?", (ext,)).fetchone():
            return None, False
        cur = c.execute(
            """INSERT INTO warnings (external_id, officer_id, subject_name, issued_at, location, reason)
               VALUES (?,?,?,?,?,?)""",
            (ext, officer_id, data.get("subject_name"), data.get("issued_at"),
             data.get("location"), data.get("reason")))
        return cur.lastrowid, True


def _row_to_warning(r):
    d = dict(r)
    d["issued_fmt"] = fmt_dt(r["issued_at"]) if r["issued_at"] else "—"
    return d


def list_warnings(limit=200, officer_id=None):
    q = """SELECT warnings.*, officers.callsign, officers.name AS officer_name
           FROM warnings LEFT JOIN officers ON officers.id = warnings.officer_id"""
    params = []
    if officer_id:
        q += " WHERE warnings.officer_id=?"; params.append(officer_id)
    q += " ORDER BY warnings.id DESC LIMIT ?"; params.append(limit)
    with get_conn() as c:
        return [_row_to_warning(r) for r in c.execute(q, params).fetchall()]


def warnings_count(officer_id=None):
    with get_conn() as c:
        if officer_id:
            return c.execute("SELECT COUNT(*) FROM warnings WHERE officer_id=?", (officer_id,)).fetchone()[0]
        return c.execute("SELECT COUNT(*) FROM warnings").fetchone()[0]


def get_citation(cit_id):
    with get_conn() as c:
        r = c.execute(
            """SELECT citations.*, officers.callsign, officers.name AS officer_name
               FROM citations LEFT JOIN officers ON officers.id = citations.officer_id
               WHERE citations.id=?""", (cit_id,)).fetchone()
        if not r:
            return None
        d = _row_to_citation(r)
        d["charges_parsed"] = [_parse_charge(x) for x in d["charges"]]
        ext = r["external_id"] or str(r["id"])
        try:
            num = int(ext.replace("-", "")[:8], 16) % 9000000 + 1000000
        except Exception:
            num = 1000000 + (r["id"] or 0)
        d["cit_no"] = f"CA-TC-{num}"
        return d


def citations_summary(officer_id=None):
    with get_conn() as c:
        if officer_id:
            r = c.execute("SELECT COUNT(*), COALESCE(SUM(fine),0) FROM citations WHERE officer_id=?",
                          (officer_id,)).fetchone()
        else:
            r = c.execute("SELECT COUNT(*), COALESCE(SUM(fine),0) FROM citations").fetchone()
        return {"count": r[0], "total_fine": r[1]}


def evidence_catalog(officer_id=None):
    """Картотека изъятого: что и сколько раз изымали."""
    q = "SELECT found_items FROM cases WHERE is_test=0"
    params = []
    if officer_id:
        q += " AND officer_id=?"; params.append(officer_id)
    counts = {}
    with get_conn() as c:
        for r in c.execute(q, params):
            for item in _jsonlist(r["found_items"]):
                key = str(item).strip()
                if key:
                    counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


# Звания и отделы LAPD (для выпадающих списков в админке)
RANKS = ["Officer I", "Officer II", "Officer III", "Detective I", "Detective II", "Detective III",
         "Sergeant I", "Sergeant II", "Lieutenant", "Watch Commander", "Captain", "Commander",
         "Deputy Chief", "Chief of Police"]
DEPARTMENTS = ["Patrol Division", "Traffic Division", "Detective Bureau", "Gang Unit",
               "Air Support", "K-9 Unit", "SWAT", "Internal Affairs", "Командование"]

STAFF_LABELS = {
    "Officer I": "Офицер I",
    "Officer II": "Офицер II",
    "Officer III": "Офицер III",
    "Detective I": "Детектив I",
    "Detective II": "Детектив II",
    "Detective III": "Детектив III",
    "Sergeant I": "Сержант I",
    "Sergeant II": "Сержант II",
    "Lieutenant": "Лейтенант",
    "Watch Commander": "Дежурный командир",
    "Captain": "Капитан",
    "Commander": "Командир",
    "Deputy Chief": "Заместитель шефа",
    "Chief of Police": "Шеф полиции",
    "Patrol Division": "Патрульный отдел",
    "Traffic Division": "Дорожный отдел",
    "Detective Bureau": "Детективное бюро",
    "LAPD Detective": "Детективный отдел",
    "METRO Division": "Отдел METRO",
    "AIR-unit LAPD": "Авиационное подразделение",
    "Training Division LAPD": "Учебный отдел",
    "Detective Division": "Детективный отдел",
    "Gang Unit": "Отдел по бандам",
    "Air Support": "Авиационная поддержка",
    "K-9 Unit": "Кинологический отдел",
    "Internal Affairs": "Внутренние расследования",
}


def staff_label(value):
    return STAFF_LABELS.get(value, value)


def list_all_officers():
    """Полный список офицеров (для страницы персонала)."""
    with get_conn() as c:
        rows = c.execute(
            """SELECT officers.*,
                      (SELECT COUNT(*) FROM cases WHERE cases.officer_id=officers.id AND cases.is_test=0) AS cases_count,
                      (SELECT COUNT(*) FROM citations WHERE citations.officer_id=officers.id) AS cit_count,
                      (SELECT COUNT(*) FROM profiles WHERE profiles.callsign=officers.callsign) AS registered
               FROM officers ORDER BY officers.is_admin DESC, officers.callsign""").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            si = status_info(d.get("current_status"))
            d["status_ru"], d["status_cls"] = si["ru"], si["cls"]
            d["rank_label"] = staff_label(d.get("rank"))
            d["department_label"] = staff_label(d.get("department"))
            d["registered"] = bool(d.get("registered"))
            out.append(d)
        return out


def update_officer_meta(officer_id, rank=None, department=None, is_admin=None, discord=None):
    with get_conn() as c:
        sets, params = [], []
        for col, val in (("rank", rank), ("department", department), ("discord", discord)):
            if val is not None:
                sets.append(f"{col}=?"); params.append(val)
        if is_admin is not None:
            sets.append("is_admin=?"); params.append(1 if is_admin else 0)
        if not sets:
            return False
        params.append(officer_id)
        c.execute(f"UPDATE officers SET {', '.join(sets)} WHERE id=?", params)
        return True


def delete_officer(officer_id):
    """Удалить офицера, если у него нет записей (чистка мусорных имён из игровых данных)."""
    with get_conn() as c:
        n = c.execute("SELECT COUNT(*) FROM cases WHERE officer_id=?", (officer_id,)).fetchone()[0]
        n += c.execute("SELECT COUNT(*) FROM citations WHERE officer_id=?", (officer_id,)).fetchone()[0]
        if n:
            return False
        c.execute("DELETE FROM status_history WHERE officer_id=?", (officer_id,))
        c.execute("DELETE FROM officers WHERE id=?", (officer_id,))
        return True


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


def activity_periods():
    """Сводка активности за 24 часа, 7 дней и 30 дней."""
    now = datetime.datetime.now()
    periods = [
        ("24 часа", now - datetime.timedelta(hours=24)),
        ("7 дней", now - datetime.timedelta(days=7)),
        ("30 дней", now - datetime.timedelta(days=30)),
    ]
    out = []
    with get_conn() as c:
        for label, start in periods:
            since = start.isoformat(timespec="seconds")
            arrests = c.execute(
                "SELECT COUNT(*) FROM cases WHERE is_test=0 AND datetime(created_at) >= datetime(?)",
                (since,),
            ).fetchone()[0]
            citations = c.execute(
                "SELECT COUNT(*), COALESCE(SUM(fine),0) FROM citations WHERE datetime(issued_at) >= datetime(?)",
                (since,),
            ).fetchone()
            court = c.execute(
                "SELECT COUNT(*) FROM court_cases WHERE datetime(filed_at) >= datetime(?)",
                (since,),
            ).fetchone()[0]
            callouts = c.execute(
                "SELECT COUNT(*) FROM callouts WHERE datetime(occurred_at) >= datetime(?)",
                (since,),
            ).fetchone()[0]
            shifts = c.execute(
                """SELECT COUNT(*), COALESCE(SUM(duration_min),0)
                   FROM shifts WHERE is_test=0 AND datetime(started_at) >= datetime(?)""",
                (since,),
            ).fetchone()
            out.append({
                "label": label,
                "arrests": arrests,
                "citations": citations[0],
                "fines_total": int(citations[1] or 0),
                "court": court,
                "callouts": callouts,
                "shifts": shifts[0],
                "shift_hours": round((shifts[1] or 0) / 60, 1),
            })
    return out


def _count_text_hits(rows, terms):
    count = 0
    for row in rows:
        text = " ".join(str(x or "") for x in row).lower()
        if any(term in text for term in terms):
            count += 1
    return count


def operation_intel():
    """Максимальная честная сводка из текущих таблиц.

    Часть показателей точная, часть помечается как найденная по тексту, потому что
    pdComp не даёт отдельные поля для эвакуаций/стрельбы/смертей.
    """
    weapon_terms = ("weapon", "firearm", "gun", "pistol", "rifle", "shotgun",
                    "оруж", "пистолет", "винтов", "дробов", "автомат")
    shooting_terms = ("shoot", "shot", "firearm", "gunfire", "стрел", "перестрел")
    evac_terms = ("tow", "impound", "evac", "эваку", "штрафстоян", "изъят транспорт")
    fatal_terms = ("killed", "dead", "fatal", "deceased", "убит", "погиб", "смерт")
    with get_conn() as c:
        arrests = c.execute("SELECT COUNT(*) FROM cases WHERE is_test=0").fetchone()[0]
        suspects = c.execute(
            "SELECT COUNT(DISTINCT suspect_name) FROM cases WHERE is_test=0 AND suspect_name!=''"
        ).fetchone()[0]
        wanted = c.execute("SELECT COUNT(*) FROM cases WHERE is_test=0 AND wanted=1").fetchone()[0]
        citations = c.execute("SELECT COUNT(*), COALESCE(SUM(fine),0) FROM citations").fetchone()
        callouts = c.execute("SELECT COUNT(*) FROM callouts").fetchone()[0]
        warnings = c.execute("SELECT COUNT(*) FROM warnings").fetchone()[0]
        courts = c.execute("SELECT COUNT(*) FROM court_cases").fetchone()[0]
        vehicles = c.execute("SELECT COUNT(DISTINCT plate) FROM vehicles WHERE plate IS NOT NULL AND plate!=''").fetchone()[0]
        case_rows = c.execute(
            "SELECT charges, found_items, reason, notes, vehicle_model, vehicle_plate FROM cases WHERE is_test=0"
        ).fetchall()
        callout_rows = c.execute("SELECT callout_type, location, zone, description, outcome FROM callouts").fetchall()

    seized_total = 0
    weapon_items = 0
    for r in case_rows:
        for item in _jsonlist(r["found_items"]):
            seized_total += 1
            if any(term in str(item).lower() for term in weapon_terms):
                weapon_items += 1
    combined = [tuple(r) for r in case_rows] + [tuple(r) for r in callout_rows]
    return {
        "arrests": arrests,
        "suspects": suspects,
        "wanted": wanted,
        "citations": citations[0],
        "fines_total": int(citations[1] or 0),
        "callouts": callouts,
        "warnings": warnings,
        "courts": courts,
        "vehicles": vehicles,
        "seized_total": seized_total,
        "weapon_items": weapon_items,
        "shooting_mentions": _count_text_hits(combined, shooting_terms),
        "evac_mentions": _count_text_hits(combined, evac_terms),
        "fatal_mentions": _count_text_hits(combined, fatal_terms),
    }


def subject_intel(name):
    """Сводка по человеку для карточки конкретного дела."""
    name = (name or "").strip()
    if not name:
        return {}
    with get_conn() as c:
        arrests = c.execute(
            "SELECT COUNT(*), COALESCE(SUM(wanted),0) FROM cases WHERE is_test=0 AND suspect_name=? COLLATE NOCASE",
            (name,),
        ).fetchone()
        citations = c.execute(
            "SELECT COUNT(*), COALESCE(SUM(fine),0) FROM citations WHERE subject_name=? COLLATE NOCASE",
            (name,),
        ).fetchone()
        warnings = c.execute(
            "SELECT COUNT(*) FROM warnings WHERE subject_name=? COLLATE NOCASE", (name,)
        ).fetchone()[0]
        courts = c.execute(
            "SELECT COUNT(*) FROM court_cases WHERE subject_name=? COLLATE NOCASE", (name,)
        ).fetchone()[0]
        callouts = c.execute(
            f"""SELECT COUNT(*) FROM callouts WHERE suspect_name=? COLLATE NOCASE
                AND NOT ({MIRROR_CALLOUT})""", (name,)
        ).fetchone()[0]
        vehicles = [r["plate"] for r in c.execute(
            "SELECT DISTINCT plate FROM vehicles WHERE suspect_name=? COLLATE NOCASE AND plate IS NOT NULL AND plate!=''",
            (name,),
        ).fetchall()]
    return {
        "arrests": arrests[0],
        "wanted": arrests[1] or 0,
        "citations": citations[0],
        "fines_total": int(citations[1] or 0),
        "warnings": warnings,
        "courts": courts,
        "callouts": callouts,
        "vehicles": vehicles,
    }


def shift_periods():
    """Сводка смен за 24 часа, неделю и месяц."""
    now = datetime.datetime.now()
    periods = [
        ("24 часа", now - datetime.timedelta(hours=24)),
        ("7 дней", now - datetime.timedelta(days=7)),
        ("30 дней", now - datetime.timedelta(days=30)),
    ]
    out = []
    with get_conn() as c:
        for label, start in periods:
            since = start.isoformat(timespec="seconds")
            row = c.execute(
                """SELECT COUNT(*), COALESCE(SUM(duration_min),0), COALESCE(SUM(arrests),0),
                          COALESCE(SUM(traffic_stops),0), COALESCE(SUM(callouts),0),
                          COALESCE(SUM(fines_total),0)
                   FROM shifts
                   WHERE is_test=0 AND datetime(started_at) >= datetime(?)""",
                (since,),
            ).fetchone()
            out.append({
                "label": label,
                "count": row[0],
                "hours": round((row[1] or 0) / 60, 1),
                "arrests": row[2] or 0,
                "traffic_stops": row[3] or 0,
                "callouts": row[4] or 0,
                "fines_total": int(row[5] or 0),
            })
    return out


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
SHIFT_TYPE_RU = {"day": "дневная", "evening": "вечерняя", "night": "ночная",
                 "patrol": "патруль", None: "—"}


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
