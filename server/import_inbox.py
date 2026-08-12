"""
Приём данных игроков без хостинга.

Каждый игрок кладёт свои записи JSON-файлом в server/inbox/ (через GitHub API).
Этот скрипт запускается на GitHub Actions, переносит их в базу и очищает папку.
Так данные попадают на сайт даже когда компьютер владельца выключен.

Формат файла inbox:
{
  "profile": {"callsign": "1-ADAM-12", "nickname": "John Miller", "discord": "user"},
  "arrests":   [ ...записи pdComp arrests.json... ],
  "citations": [ ...записи pdComp citations.json... ],
  "cases":     [ ...записи pdComp cases.json... ]
}
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

from app import db                    # noqa: E402

INBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inbox")
PENDING = os.path.join(INBOX, "pending")
ROSTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roster.json")

# Supabase — источник одобрений с сайта (кнопка «Одобрить» / авто-режим).
# Publishable-ключ публичный (тот же, что на сайте), запись защищена RLS.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://gwvqfiwdbviwoimvhdvg.supabase.co").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_gkXQmLngTvpGQfLFDk2YnA_nuv0krkk")

# заполняется load_supabase_moderation()
SB_CALLSIGNS = set()   # одобренные позывные (нижний регистр) из Supabase roster
AUTO_APPROVE = False   # включён ли режим «одобрять всех»
_SB_OK = False         # удалось ли связаться с Supabase


def _sb_get(path):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def _sb_rpc(fn, payload):
    url = f"{SUPABASE_URL}/rest/v1/rpc/{fn}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def load_supabase_moderation():
    """Тянет из Supabase список одобренных позывных и флаг авто-одобрения.
    Если Supabase недоступен/не настроен — тихо откатываемся на roster.json."""
    global SB_CALLSIGNS, AUTO_APPROVE, _SB_OK
    try:
        rows = _sb_get("roster?select=callsign")
        SB_CALLSIGNS = {(r.get("callsign") or "").strip().lower() for r in rows if r.get("callsign")}
        mod = _sb_get("moderation?select=auto_approve&id=eq.1")
        AUTO_APPROVE = bool(mod and mod[0].get("auto_approve"))
        _SB_OK = True
        print(f"[supabase] одобренных: {len(SB_CALLSIGNS)}, авто-одобрение: {'ВКЛ' if AUTO_APPROVE else 'выкл'}")
    except Exception as e:
        _SB_OK = False
        print(f"[supabase] недоступен ({e}) — использую только roster.json")


def report_pending(callsign, name, discord):
    """Сообщает сайту, что появился неодобренный офицер (для раздела «Модерация»)."""
    if not _SB_OK:
        return
    try:
        _sb_rpc("report_pending", {"_callsign": callsign, "_name": name or None,
                                   "_discord": discord or None})
    except Exception:
        pass   # не критично — просто не покажем в модерации


def load_roster():
    """Одобренные офицеры. Ключи — discord и позывной (нижний регистр)."""
    try:
        data = json.load(open(ROSTER, encoding="utf-8"))
    except Exception:
        return {}
    approved = {}
    for key, info in (data.get("approved") or {}).items():
        approved[key.strip().lower()] = info
        cs = (info.get("callsign") or "").strip().lower()
        if cs:
            approved[cs] = info
    return approved


def is_approved(roster, callsign, discord):
    """Одобрен, если: включён авто-режим, ИЛИ позывной есть в Supabase-реестре,
    ИЛИ discord/позывной есть в roster.json (легаси-фолбэк)."""
    if AUTO_APPROVE:
        return True
    cs = (callsign or "").strip().lower()
    if cs and cs in SB_CALLSIGNS:
        return True
    if not roster and not _SB_OK:
        return True   # ни ростера, ни Supabase — первичная настройка, приём открыт
    for key in ((discord or "").strip().lower(), cs):
        if key and key in roster:
            return True
    return False


def _map_arrest(a, callsign, nickname):
    charges = []
    for c in a.get("Charges", []):
        line = f"{c.get('ChargeCode','')} · {c.get('Description','')}".strip(" ·")
        if c.get("LegalClass"):
            line += f" ({c['LegalClass']})"
        charges.append(line)
    return {
        "external_id": a.get("Id"),
        "callsign": callsign,
        "officer_name": nickname,
        "suspect_name": a.get("SubjectFullName") or "Неизвестный",
        "zone": _fix(a.get("Location")),
        "game_time": a.get("ArrestedAtWall") or a.get("ArrestedAt"),
        "charges": charges,
        "found_items": [e.get("Description", "") for e in a.get("Evidence", []) if e.get("Description")],
        "notes": a.get("Narrative"),
        "is_test": False,
    }


def _map_citation(ct, callsign, nickname):
    charges, fine = [], 0.0
    for c in (ct.get("Lines") or []):
        charges.append(f"{c.get('ChargeCode','')} · {c.get('Description','')}".strip(" ·"))
        fine += float(c.get("Fine") or 0)
    return {
        "external_id": ct.get("Id"),
        "callsign": callsign,
        "officer_name": nickname,
        "subject_name": ct.get("SubjectFullName") or "Неизвестный",
        "issued_at": ct.get("IssuedAtWall") or ct.get("IssuedAt"),
        "location": _fix(ct.get("Location")),
        "charges": charges,
        "fine": int(round(fine)),
        "notes": ct.get("Notes"),
    }


def _map_case(cc):
    return {
        "external_id": cc.get("Id"),
        "subject_name": cc.get("SubjectFullName") or "Неизвестный",
        "source": "Арест" if cc.get("ArrestReportId") else "Штраф",
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


def _feed(rec, kind, record_id=None):
    """Отправить карточку события в Discord (если задан вебхук)."""
    try:
        from app import discord_post
        ok, msg = discord_post.send_feed(rec, kind, record_id=record_id)
        if ok:
            print(f"   [discord] {kind}: {rec.get('suspect_name') or rec.get('subject_name')}")
    except Exception as e:
        print(f"   [discord] не отправлено: {e}")


def _fix(s):
    """Чинит адреса, побитые двойной кодировкой (UTF-8, прочитанный как CP1251).
    Символы вне таблицы cp1251 (например U+0098 из «И») отдаём одним байтом,
    иначе адреса вида «Р‘СѓР»СЊРІР°СЂ РРЅРЅРѕСЃРµРЅСЃ» остаются битыми."""
    if not s:
        return s
    out = bytearray()
    try:
        for ch in s:
            try:
                out += ch.encode("cp1251")
            except UnicodeEncodeError:
                code = ord(ch)
                if code >= 256:
                    return s
                out.append(code)
        return bytes(out).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return s


def _repromote_pending(roster):
    """Возвращает из модерации в inbox тех, кого уже одобрили (Supabase/roster.json),
    или всех при авто-режиме. Так одобрение кнопкой на сайте публикуется само."""
    if not os.path.isdir(PENDING):
        return 0
    moved = 0
    for fname in sorted(f for f in os.listdir(PENDING) if f.endswith(".json")):
        pth = os.path.join(PENDING, fname)
        try:
            prof = (json.load(open(pth, encoding="utf-8")).get("profile") or {})
        except Exception:
            continue
        callsign = (prof.get("callsign") or "").strip()
        discord = (prof.get("discord") or "").strip()
        if callsign and is_approved(roster, callsign, discord):
            os.replace(pth, os.path.join(INBOX, fname))
            moved += 1
    if moved:
        print(f"[модерация] одобренных возвращено из pending: {moved}")
    return moved


def main():
    os.makedirs(INBOX, exist_ok=True)
    os.makedirs(PENDING, exist_ok=True)
    load_supabase_moderation()
    roster = load_roster()
    _repromote_pending(roster)   # одобренные с сайта → назад в inbox на публикацию

    files = sorted(f for f in os.listdir(INBOX) if f.endswith(".json"))
    if not files:
        print("Inbox пуст — новых данных от игроков нет.")
        return

    db.init_db()
    total_a = total_c = total_ct = total_s = 0
    parked = 0

    for fname in files:
        path = os.path.join(INBOX, fname)
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            print(f"[пропуск] {fname}: не читается ({e})")
            continue

        prof = data.get("profile") or {}
        callsign = (prof.get("callsign") or "").strip()
        nickname = (prof.get("nickname") or "").strip()
        discord = (prof.get("discord") or "").strip()
        if not callsign:
            print(f"[пропуск] {fname}: нет позывного")
            continue

        # МОДЕРАЦИЯ: неодобренный офицер → в pending + показать на сайте в «Модерации»
        if not is_approved(roster, callsign, discord):
            os.replace(path, os.path.join(PENDING, fname))
            report_pending(callsign, nickname, discord)
            parked += 1
            print(f"[на модерацию] {fname} — {callsign} (discord: {discord or '—'}) не одобрен")
            continue

        db.register_profile(f"inbox-{callsign}", callsign, nickname or callsign,
                            prof.get("discord"))

        for a in data.get("arrests", []):
            if not db.case_exists_external(a.get("Id")):
                rec = _map_arrest(a, callsign, nickname)
                cid = db.create_case(rec)
                db.ensure_callout_for_case(rec, cid)
                _feed(rec, "arrest", cid)
                total_a += 1
        for ct in data.get("citations", []):
            rec = _map_citation(ct, callsign, nickname)
            cit_id, created = db.upsert_citation(rec)
            if created:
                _feed(rec, "citation", cit_id)
                total_ct += 1
        for cc in data.get("cases", []):
            _, created = db.upsert_court_case(_map_case(cc))
            if created:
                total_c += 1
        for sh in data.get("shifts", []):
            sh.setdefault("callsign", callsign)
            sh.setdefault("officer_name", nickname)
            _sid = db.create_shift(sh)
            total_s += 1
            try:
                from app import discord_post
                discord_post.send_shift(db.get_shift(_sid))   # рапорт смены → Discord
            except Exception:
                pass
        for w in data.get("warnings", []):
            w.setdefault("callsign", callsign)
            w.setdefault("officer_name", nickname)
            _, created = db.upsert_warning(w)
            if created:
                _feed(w, "warning")

        # настоящие вызовы LSPDFR из плагина (в отличие от CAD-зеркал задержаний)
        for co in data.get("live_callouts", []):
            co.setdefault("callsign", callsign)
            co.setdefault("officer_name", nickname)
            co["callout_type"] = _fix(co.get("callout_type"))
            _cid, created = db.create_callout(co)
            if created:
                print(f"   [вызов] {co.get('callout_type')}")

        # живые данные из игрового плагина DispatchOne.MDT
        for p in data.get("ped_checks", []):
            p.setdefault("callsign", callsign)
            db.record_ped_document(p)
        for v in data.get("plate_checks", []):
            v.setdefault("callsign", callsign)
            db.record_vehicle_check(v)
        duty_seen = False
        for d in data.get("duty_events", []):
            d.setdefault("callsign", callsign)
            if db.record_duty_event(d):
                duty_seen = True
        if duty_seen:
            db.sync_duty_shifts(callsign, nickname)

        os.remove(path)     # приняли — убираем из inbox
        print(f"[принято] {fname} — офицер {callsign}")

    print(f"Итого принято: задержаний {total_a}, штрафов {total_ct}, "
          f"судебных дел {total_c}, смен {total_s}")
    if parked:
        print(f"На модерации (неизвестные офицеры): {parked} — одобри их в разделе «Персонал»")


if __name__ == "__main__":
    main()
