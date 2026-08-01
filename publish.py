"""
Dispatch One — обновить публичный сайт (GitHub Pages) свежими данными из игры.

Что делает: читает данные pdComp (аресты, суд) → пишет в базу → рендерит статику → пушит на GitHub.
Сайт живёт 24/7 и не зависит от того, включён ли твой компьютер.

Запуск:  py publish.py     (или «Обновить сайт.bat»)
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "agent"))

from app import db                      # noqa: E402
import pdcomp_sync as agent             # noqa: E402


def known_officers():
    """Имена зарегистрированных офицеров — только их записи попадают на сайт."""
    names = set()
    with db.get_conn() as c:
        for r in c.execute("SELECT nickname, callsign FROM profiles"):
            for v in (r["nickname"], r["callsign"]):
                if v:
                    names.add(v.strip().lower())
    return names


def sync_from_game():
    """Читает pdComp напрямую и пишет в базу (без HTTP).
    Записи чужих/демонстрационных офицеров пропускаются — статистика честная."""
    db.init_db()
    known = known_officers()

    # профиль владельца (из регистрации) — под ним пишутся записи локального игрока
    with db.get_conn() as c:
        row = c.execute("SELECT callsign, nickname FROM profiles ORDER BY updated_at LIMIT 1").fetchone()
    if row:
        agent._PROFILE = {"callsign": row["callsign"], "nickname": row["nickname"]}
        print(f"   профиль: {row['callsign']} ({row['nickname']})")
    new_arrests = new_court = 0
    skipped = 0

    # pdComp пишет "Officer" (или пусто), если имя офицера не задано в его настройках —
    # это записи локального игрока, то есть наши.
    GENERIC = {"", "officer", "unknown", "n/a", "-"}

    def is_ours(officer_name):
        nm = (officer_name or "").strip().lower()
        if nm in GENERIC:
            return True
        if not known:
            return True
        return nm in known

    arrests = agent.read_json(os.path.join(agent.PDCOMP_STORE, "arrests.json")) or []
    for a in arrests:
        if not is_ours(a.get("OfficerName")):
            skipped += 1
            continue
        data = agent.map_arrest(a)
        if not db.case_exists_external(data.get("external_id")):
            db.create_case(data)
            _feed_event(data, "arrest")
            new_arrests += 1

    # Судебные дела берём только по нашим арестам/штрафам
    our_sources = set()
    for a in arrests:
        if is_ours(a.get("OfficerName")) and a.get("Id"):
            our_sources.add(a["Id"])
    cits_raw = agent.read_json(os.path.join(agent.PDCOMP_STORE, "citations.json")) or []
    for ct in cits_raw:
        if is_ours(ct.get("OfficerName")) and ct.get("Id"):
            our_sources.add(ct["Id"])

    cases = agent.read_json(os.path.join(agent.PDCOMP_STORE, "cases.json")) or []
    for c in cases:
        src = c.get("CitationId") or c.get("ArrestReportId")
        # если знаем своих офицеров — берём только дела по нашим записям
        if known and src not in our_sources:
            skipped += 1
            continue
        _, created = db.upsert_court_case(agent.map_court_case(c))
        if created:
            new_court += 1

    new_cit = 0
    cits = agent.read_json(os.path.join(agent.PDCOMP_STORE, "citations.json")) or []
    for ct in cits:
        if not is_ours(ct.get("OfficerName")):
            skipped += 1
            continue
        cit_data = agent.map_citation(ct)
        _, created = db.upsert_citation(cit_data)
        if created:
            _feed_event(cit_data, "citation")
            new_cit += 1

    # смены из очереди агента (владелец)
    new_shifts = 0
    shift_queue = os.path.join(ROOT, "pending_shifts.json")
    if os.path.exists(shift_queue):
        try:
            for sh in json.load(open(shift_queue, encoding="utf-8")):
                db.create_shift(sh)
                new_shifts += 1
            os.remove(shift_queue)
        except Exception as e:
            print(f"   смены не приняты: {e}")

    return new_arrests, new_court, len(arrests), len(cases), new_cit, len(cits), skipped, new_shifts


def _feed_event(rec, kind):
    """Отправить событие в ленту Discord, если задан вебхук."""
    try:
        from app import discord_post
        discord_post.send_feed(rec, kind)
    except Exception:
        pass


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)


def main():
    print("1) Читаю данные из игры (pdComp)...")
    na, nc, ta, tc, ncit, tcit, skipped, nsh = sync_from_game()
    print(f"   аресты: {ta} (новых {na}) | суд: {tc} (новых {nc}) | штрафы: {tcit} (новых {ncit})")
    if nsh:
        print(f"   смен добавлено: {nsh}")
    if skipped:
        print(f"   пропущено чужих/демо записей: {skipped}")

    print("2) Собираю сайт...")
    r = run([sys.executable, os.path.join(ROOT, "server", "export_static.py")])
    print("   " + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "готово"))

    print("3) Публикую на GitHub Pages...")
    run("git add -A docs")
    st = run("git status --porcelain docs")
    if not st.stdout.strip():
        print("   изменений нет — сайт уже актуален")
        return
    run('git commit -q -m "Обновление данных сайта из игры"')
    p = run("git push -q origin main")
    if p.returncode == 0:
        print("   ОПУБЛИКОВАНО")
        print("\nСайт: https://osminoog09-star.github.io/dispatch-one-records/")
        print("(обновится на сервере GitHub в течение ~1 минуты)")
    else:
        print("   ошибка публикации:", (p.stderr or "")[:300])


if __name__ == "__main__":
    main()
