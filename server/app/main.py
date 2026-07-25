"""Flask-приложение Records: приём дел от мода (авто) + сайт + постинг в Discord по кнопке."""
import os
import time
import random

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_from_directory, abort)

import config
from app import db, discord_post

app = Flask(__name__)
app.secret_key = os.environ.get("RECORDS_SECRET", "records-dev-secret")

os.makedirs(config.SCREENSHOT_DIR, exist_ok=True)
db.init_db()


@app.context_processor
def inject_globals():
    return {"community": config.COMMUNITY_NAME, "STATUS_RU": db.STATUS_RU,
            "static_export": os.environ.get("STATIC_EXPORT") == "1"}


# ---------- Сайт ----------
@app.route("/")
def index():
    cases_all = db.list_cases(500)
    zones = {}
    for c in cases_all:
        if not c.get("is_test") and c.get("zone"):
            zones[c["zone"]] = zones.get(c["zone"], 0) + 1
    top = sorted(zones.items(), key=lambda kv: -kv[1])[:10]
    mx = top[0][1] if top else 1
    districts = [{"zone": z, "count": n, "pct": round(n * 100 / mx)} for z, n in top]

    return render_template("index.html",
                           summary=db.summary_counts(),
                           cases=db.list_cases(limit=8),
                           officers=db.list_officers_with_stats(),
                           cit=db.citations_summary(),
                           court=db.court_summary(),
                           districts=districts,
                           evidence=db.evidence_catalog())


# Районы Лос-Сантоса и округа Блэйн — позиции на схеме карты (x, y, радиус)
MAP_ZONES = [
    # ===== ОКРУГ БЛЭЙН (север) =====
    ("Paleto Bay",        246,  92, 26),   # крайний север
    ("Mount Chiliad",     188, 150, 24),   # гора, северо-запад
    ("Grapeseed",         432, 176, 26),   # северо-восток, фермы
    ("Sandy Shores",      432, 268, 27),   # восточный берег Аламо
    ("Harmony",           286, 320, 22),   # запад от озера
    ("Grand Senora",      368, 352, 26),   # пустыня, юг Блэйна
    ("Chumash",           132, 372, 24),   # западное побережье
    # ===== ЛОС-САНТОС (юг) =====
    ("Vinewood Hills",    286, 502, 26),   # холмы над городом
    ("Downtown Vinewood", 360, 512, 26),   # Вайнвуд
    ("Mirror Park",       424, 546, 24),   # восточнее центра
    ("Del Perro",         186, 552, 24),   # северо-западный пляж
    ("Downtown",          318, 566, 24),   # деловой центр
    ("Mission Row",       360, 592, 24),   # участок полиции
    ("La Mesa",           420, 596, 22),   # промзона восток
    ("Vespucci",          176, 606, 24),   # пляж
    ("El Burro Heights",  456, 640, 24),   # юго-восток
    ("Strawberry",        306, 638, 24),   # южнее центра
    ("Rancho",            378, 656, 22),   # юго-восток города
    ("Davis",             330, 690, 24),   # юг
    ("Puerto Del Sol",    214, 664, 24),   # порт, юго-запад
]


def _best_zone(text):
    """Определяет район записи: берём самое длинное (точное) совпадение, чтобы
    'Downtown Vinewood' не засчитывался ещё и в 'Downtown'."""
    if not text:
        return None
    low = text.lower()
    best = None
    for name, *_ in MAP_ZONES:
        if name.lower() in low and (best is None or len(name) > len(best)):
            best = name
    return best


@app.route("/map")
def game_map():
    cases = [c for c in db.list_cases(500) if not c.get("is_test")]
    cits = db.list_citations(500)

    arr_by_zone, cit_by_zone = {}, {}
    for c in cases:
        z = _best_zone(c.get("zone"))
        if z:
            arr_by_zone[z] = arr_by_zone.get(z, 0) + 1
    for c in cits:
        z = _best_zone(c.get("location"))
        if z:
            cit_by_zone[z] = cit_by_zone.get(z, 0) + 1

    zones = []
    for name, x, y, r in MAP_ZONES:
        arrests = arr_by_zone.get(name, 0)
        citations_n = cit_by_zone.get(name, 0)
        zones.append({"name": name, "x": x, "y": y, "r": r,
                      "arrests": arrests, "citations": citations_n,
                      "count": arrests + citations_n})
    mx = max([z["count"] for z in zones] + [1])
    for z in zones:
        z["intensity"] = round(z["count"] / mx, 2) if mx else 0

    top = sorted([z for z in zones if z["count"]], key=lambda z: -z["count"])[:8]
    top_zones = [{"zone": z["name"], "count": z["count"],
                  "pct": round(z["count"] * 100 / mx)} for z in top]

    return render_template("map.html", map_districts=zones, top_zones=top_zones)


@app.route("/staff", methods=["GET", "POST"])
def staff():
    is_static = os.environ.get("STATIC_EXPORT") == "1"
    if request.method == "POST" and not is_static:
        oid = request.form.get("officer_id", type=int)
        if request.form.get("action") == "delete":
            flash("Офицер удалён." if db.delete_officer(oid) else "Нельзя удалить: есть записи.",
                  "ok" if db.delete_officer(oid) else "err")
        else:
            db.update_officer_meta(oid,
                                   rank=request.form.get("rank"),
                                   department=request.form.get("department"),
                                   discord=request.form.get("discord"),
                                   is_admin=bool(request.form.get("is_admin")))
            flash("Сохранено.", "ok")
        return redirect(url_for("staff"))
    return render_template("staff.html", officers=db.list_all_officers(),
                           ranks=db.RANKS, departments=db.DEPARTMENTS)


@app.route("/citations")
def citations():
    return render_template("citations.html", citations=db.list_citations(300),
                           summary=db.citations_summary())


@app.route("/cases")
def cases():
    status = request.args.get("status") or None
    return render_template("cases.html", cases=db.list_cases(200, status=status),
                           statuses=db.STATUSES, active_status=status)


@app.route("/case/<int:cid>")
def case_view(cid):
    case = db.get_case(cid)
    if not case:
        abort(404)
    discord_md = discord_post.build_markdown(case)
    return render_template("case.html", case=case, statuses=db.STATUSES, discord_md=discord_md)


@app.route("/case/<int:cid>/discord", methods=["POST"])
def case_discord(cid):
    case = db.get_case(cid)
    if not case:
        abort(404)
    ok, msg = discord_post.send_case(case)
    flash(msg, "ok" if ok else "err")
    return redirect(url_for("case_view", cid=cid))


@app.route("/case/<int:cid>/status", methods=["POST"])
def case_status(cid):
    if db.set_status(cid, request.form.get("status", "")):
        flash("Статус обновлён.", "ok")
    else:
        flash("Неверный статус.", "err")
    return redirect(url_for("case_view", cid=cid))


@app.route("/officer/<callsign>")
def officer_view(callsign):
    off = db.get_officer(callsign)
    if not off:
        abort(404)
    shifts = db.list_shifts(50, officer_id=off["id"])
    hours = round(sum(s.get("duration_min") or 0 for s in shifts) / 60, 1)
    return render_template("officer.html", officer=off,
                           cases=db.list_cases(200, officer_id=off["id"]),
                           citations=db.list_citations(200, officer_id=off["id"]),
                           cit=db.citations_summary(off["id"]),
                           evidence=db.evidence_catalog(off["id"]),
                           shifts=shifts, hours=hours)


@app.route("/register", methods=["GET", "POST"])
def register():
    if os.environ.get("STATIC_EXPORT") == "1" or request.method == "GET":
        return render_template("register.html")
    token = request.values.get("token") or None
    if request.method == "POST":
        callsign = (request.form.get("callsign") or "").strip()
        nickname = (request.form.get("nickname") or "").strip()
        discord = (request.form.get("discord") or "").strip()
        if not callsign or not nickname:
            flash("Заполни позывной и никнейм.", "err")
        else:
            if not token:
                token = db.new_token()
            db.register_profile(token, callsign, nickname, discord)
            flash("Профиль сохранён. Скопируй ключ в агент.", "ok")
            return render_template("register.html", token=token, saved=True,
                                   callsign=callsign, nickname=nickname, discord=discord)
    prof = db.get_profile(token) if token else None
    return render_template("register.html", token=token,
                           callsign=(prof or {}).get("callsign"),
                           nickname=(prof or {}).get("nickname"),
                           discord=(prof or {}).get("discord"))


@app.route("/api/profile")
def api_profile():
    key = request.headers.get("X-Api-Key") or request.args.get("api_key")
    prof = db.get_profile(key) if key else None
    if not prof:
        return jsonify({"error": "not_registered"}), 404
    return jsonify({"callsign": prof["callsign"], "nickname": prof["nickname"]})


@app.route("/court")
def court():
    return render_template("court.html", cases=db.list_court_cases(200), summary=db.court_summary())


@app.route("/court/<int:cid>")
def court_case_view(cid):
    case = db.get_court_case(cid)
    if not case:
        abort(404)
    return render_template("court_case.html", case=case,
                           discord_md=discord_post.build_court_markdown(case))


@app.route("/api/court", methods=["POST"])
def api_court():
    key = request.headers.get("X-Api-Key") or request.form.get("api_key")
    if key != config.API_KEY:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or request.form.to_dict()
    cid, created = db.upsert_court_case(data)
    return jsonify({"ok": True, "id": cid, "created": created}), (201 if created else 200)


@app.route("/shifts")
def shifts():
    return render_template("shifts.html", shifts=db.list_shifts(200))


@app.route("/shift/<int:sid>")
def shift_view(sid):
    shift = db.get_shift(sid)
    if not shift:
        abort(404)
    return render_template("shift.html", shift=shift,
                           discord_md=discord_post.build_shift_markdown(shift))


@app.route("/screenshots/<path:fn>")
def screenshot(fn):
    return send_from_directory(config.SCREENSHOT_DIR, fn)


# ---------- API для мода (авто-приём дела) ----------
@app.route("/api/case", methods=["POST"])
def api_case():
    key = request.headers.get("X-Api-Key") or request.form.get("api_key")
    if key != config.API_KEY:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or request.form.to_dict()
    # дедуп по ID из игры — чтобы не задваивать один и тот же арест
    existing = db.case_exists_external(data.get("external_id"))
    if existing:
        return jsonify({"ok": True, "case_id": existing, "duplicate": True}), 200
    if "screenshot" in request.files:
        f = request.files["screenshot"]
        safe = f"case_{int(time.time())}_{os.path.basename(f.filename)}"
        f.save(os.path.join(config.SCREENSHOT_DIR, safe))
        data["screenshot"] = safe

    cid = db.create_case(data)
    return jsonify({"ok": True, "case_id": cid}), 201


@app.route("/api/shift", methods=["POST"])
def api_shift():
    key = request.headers.get("X-Api-Key") or request.form.get("api_key")
    if key != config.API_KEY:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or request.form.to_dict()
    sid = db.create_shift(data)
    return jsonify({"ok": True, "shift_id": sid}), 201


@app.route("/api/status", methods=["POST"])
def api_status():
    key = request.headers.get("X-Api-Key") or request.form.get("api_key")
    if key != config.API_KEY:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or request.form.to_dict()
    db.set_officer_status(data.get("callsign", "UNKNOWN"), data.get("status", "10-7"),
                          data.get("officer_name"))
    return jsonify({"ok": True}), 200


# ---------- Dev-хелпер: создать тестовое дело (без игры) ----------
@app.route("/dev/seed")
def dev_seed():
    names = ["Джон Доу", "Майкл Смит", "Карлос Рамирес", "Анна Джонсон", "Дмитрий Волков"]
    zones = ["Vinewood Hills", "Del Perro", "Strawberry", "Sandy Shores", "Downtown"]
    lic = ["Valid", "Suspended", "Expired", "Unlicensed"]
    vehicles = [("Bravado Buffalo", "чёрный"), ("Declasse Sabre", "красный"),
                ("Vapid Dominator", "синий"), ("Karin Sultan", "белый"), ("Обеспечьте пешком", "—")]
    contraband_pool = ["Пистолет Pistol .50", "Марихуана (24 г)", "Крупная сумма наличных ($4200)",
                       "Краденый телефон", "Нож", "Кокаин (5 г)"]
    reasons = ["Остановка транспорта — нарушение ПДД", "Подозрительное поведение",
               "Реакция на вызов", "Проверка по ориентировке"]

    veh, color = random.choice(vehicles)
    found = random.sample(contraband_pool, k=random.randint(0, 3))
    data = {
        "callsign": "7-WILLIAM-1", "officer_name": config.OFFICER_NAME,
        "suspect_name": random.choice(names),
        "wanted": random.choice([True, False, False]),
        "license_state": random.choice(lic),
        "citations": random.randint(0, 6),
        "zone": random.choice(zones), "postal": str(random.randint(1000, 9999)),
        "game_time": f"{random.randint(0,23):02d}:{random.randint(0,59):02d}",
        "vehicle_model": veh if veh != "Обеспечьте пешком" else None,
        "vehicle_plate": None if veh == "Обеспечьте пешком" else "".join(random.choice("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(8)),
        "vehicle_color": None if veh == "Обеспечьте пешком" else color,
        "found_items": found,
        "reason": random.choice(reasons),
        "notes": "Задержанный доставлен в участок. Сопротивления не оказывал.",
        "fine": random.choice([0, 250, 500, 750, 1200]),
        "bail": random.choice([0, 1000, 2500, 5000]),
        "jail_time": random.choice(["—", "5 суток", "30 суток", "6 месяцев", "2 года"]),
        "is_test": True,   # тестовое дело — не идёт в честную статистику
    }
    cid = db.create_case(data)
    flash(f"Создано ТЕСТОВОЕ дело #{cid} (в статистику не входит).", "ok")
    return redirect(url_for("case_view", cid=cid))


@app.route("/dev/seed-shift")
def dev_seed_shift():
    dur = random.randint(45, 240)
    arrests = random.randint(0, 6)
    data = {
        "callsign": "7-WILLIAM-1", "officer_name": config.OFFICER_NAME,
        "shift_type": random.choice(["day", "evening", "night"]),
        "duration_min": dur,
        "arrests": arrests,
        "traffic_stops": random.randint(arrests, arrests + 10),
        "pursuits": random.randint(0, 4),
        "pit": random.randint(0, 3),
        "callouts": random.randint(0, 8),
        "fines_total": random.choice([0, 500, 1200, 2400, 3600]),
        "is_test": True,
    }
    sid = db.create_shift(data)
    flash(f"Создан ТЕСТОВЫЙ рапорт смены #{sid}.", "ok")
    return redirect(url_for("shift_view", sid=sid))


@app.route("/dev/status/<code>")
def dev_status(code):
    db.set_officer_status("7-WILLIAM-1", code, config.OFFICER_NAME)
    flash(f"Статус офицера изменён: {db.status_info(code)['ru']}.", "ok")
    return redirect(url_for("officer_view", callsign="7-WILLIAM-1"))


@app.route("/dev/clear-tests")
def dev_clear_tests():
    n = db.delete_test_cases()
    flash(f"Удалено тестовых дел: {n}.", "ok")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
