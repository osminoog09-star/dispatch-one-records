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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

from app import db                    # noqa: E402

INBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inbox")


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


def _fix(s):
    """Чинит адреса, побитые двойной кодировкой."""
    if not s:
        return s
    try:
        return s.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def main():
    os.makedirs(INBOX, exist_ok=True)
    files = sorted(f for f in os.listdir(INBOX) if f.endswith(".json"))
    if not files:
        print("Inbox пуст — новых данных от игроков нет.")
        return

    db.init_db()
    total_a = total_c = total_ct = 0

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
        if not callsign:
            print(f"[пропуск] {fname}: нет позывного")
            continue

        db.register_profile(f"inbox-{callsign}", callsign, nickname or callsign,
                            prof.get("discord"))

        for a in data.get("arrests", []):
            if not db.case_exists_external(a.get("Id")):
                db.create_case(_map_arrest(a, callsign, nickname))
                total_a += 1
        for ct in data.get("citations", []):
            _, created = db.upsert_citation(_map_citation(ct, callsign, nickname))
            if created:
                total_ct += 1
        for cc in data.get("cases", []):
            _, created = db.upsert_court_case(_map_case(cc))
            if created:
                total_c += 1

        os.remove(path)     # приняли — убираем из inbox
        print(f"[принято] {fname} — офицер {callsign}")

    print(f"Итого принято: задержаний {total_a}, штрафов {total_ct}, судебных дел {total_c}")


if __name__ == "__main__":
    main()
