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


def sync_from_game():
    """Читает pdComp напрямую и пишет в базу (без HTTP)."""
    db.init_db()
    new_arrests = new_court = 0

    arrests = agent.read_json(os.path.join(agent.PDCOMP_STORE, "arrests.json")) or []
    for a in arrests:
        data = agent.map_arrest(a)
        if not db.case_exists_external(data.get("external_id")):
            db.create_case(data)
            new_arrests += 1

    cases = agent.read_json(os.path.join(agent.PDCOMP_STORE, "cases.json")) or []
    for c in cases:
        _, created = db.upsert_court_case(agent.map_court_case(c))
        if created:
            new_court += 1

    return new_arrests, new_court, len(arrests), len(cases)


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)


def main():
    print("1) Читаю данные из игры (pdComp)...")
    na, nc, ta, tc = sync_from_game()
    print(f"   аресты: всего {ta}, новых {na} | суд: всего {tc}, новых {nc}")

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
