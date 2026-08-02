"""Отправка красивой карточки дела в Discord через webhook (по кнопке с сайта)."""
import os
import requests

import config
from app import db

# Цвета embed по статусу/розыску
COLOR_WANTED = 0xC0392B   # красный — в розыске
COLOR_NORMAL = 0x2E5C8A   # синий — обычное


def build_embed(case):
    wanted = case["wanted"]
    charges = case.get("charges") or []
    found = case.get("found_items") or []
    veh = case.get("vehicle_model")
    veh_val = "—"
    if veh:
        veh_val = veh + (f" · {case['vehicle_color']}" if case.get("vehicle_color") else "")
        if case.get("vehicle_plate"):
            veh_val += f" · {case['vehicle_plate']}"

    fields = [
        {"name": "Подозреваемый", "value": case.get("suspect_name") or "Неизвестный", "inline": True},
        {"name": "Статус розыска", "value": "🔴 В розыске" if wanted else "🟢 Чисто", "inline": True},
        {"name": "Права", "value": case.get("license_ru") or "—", "inline": True},
        {"name": "Причина", "value": case.get("reason") or "—", "inline": False},
        {"name": "Статьи", "value": ("\n".join("• " + c for c in charges)) if charges else "—", "inline": False},
        {"name": "Транспорт", "value": veh_val, "inline": True},
        {"name": "Изъято", "value": (", ".join(found)) if found else "—", "inline": True},
        {"name": "Район", "value": (case.get("zone") or "—") + (f" · {case['postal']}" if case.get("postal") else ""), "inline": True},
        {"name": "Время", "value": case.get("game_time") or "—", "inline": True},
        {"name": "Офицер", "value": case.get("callsign") or "—", "inline": True},
        {"name": "Наказание", "value": f"Штраф ${case.get('fine') or 0} · Залог ${case.get('bail') or 0} · Срок {case.get('jail_time') or '—'}", "inline": False},
        {"name": "Статус дела", "value": case.get("status_ru") or "—", "inline": True},
    ]
    if case.get("created_fmt"):
        embed_ts = {"name": "Задержание", "value": case["created_fmt"], "inline": True}
        fields.insert(-1, embed_ts)
    embed = {
        "title": f"Рапорт о задержании · Дело #{case['id']}",
        "color": COLOR_WANTED if wanted else COLOR_NORMAL,
        "fields": fields,
        "footer": {"text": f"{config.COMMUNITY_NAME} · Dispatch One Records"},
    }
    return embed


def build_markdown(case):
    """Готовый текст рапорта для ручной вставки в Discord (markdown)."""
    L = []
    L.append(f"📋 **Рапорт о задержании · Дело #{case['id']}**")
    wanted = "🔴 В розыске" if case.get("wanted") else "🟢 Чисто"
    L.append(f"**Подозреваемый:** {case.get('suspect_name') or 'Неизвестный'} — {wanted}")
    if case.get("reason"):
        L.append(f"**Причина:** {case['reason']}")
    charges = case.get("charges") or []
    if charges:
        L.append("**Статьи:**")
        L.extend(f"• {c}" for c in charges)
    if case.get("vehicle_model"):
        veh = case["vehicle_model"]
        if case.get("vehicle_color"):
            veh += f" · {case['vehicle_color']}"
        if case.get("vehicle_plate"):
            veh += f" · {case['vehicle_plate']}"
        L.append(f"**Транспорт:** {veh}")
    found = case.get("found_items") or []
    if found:
        L.append(f"**Изъято:** {', '.join(found)}")
    loc = case.get("zone") or "—"
    if case.get("postal"):
        loc += f" · инд. {case['postal']}"
    if case.get("game_time"):
        loc += f" · {case['game_time']}"
    L.append(f"**Место/время:** {loc}")
    if case.get("fine") or case.get("bail") or (case.get("jail_time") and case["jail_time"] != "—"):
        L.append(f"**Наказание:** Штраф ${case.get('fine') or 0} · Залог ${case.get('bail') or 0} · Срок {case.get('jail_time') or '—'}")
    officer = case.get("callsign") or "—"
    if case.get("officer_name"):
        officer += f" ({case['officer_name']})"
    L.append(f"**Офицер:** {officer}")
    L.append(f"*Статус: {case.get('status_ru') or '—'} · задержание {case.get('created_fmt') or ''}*")
    return "\n".join(L)


def build_court_markdown(c):
    """Готовый текст судебного дела для вставки в Discord."""
    L = []
    L.append(f"⚖ **Уголовное дело · {c.get('subject_name') or 'Неизвестный'}**")
    L.append(f"**Статус:** {c.get('label') or '—'}")
    charges = c.get("charges") or []
    if charges:
        L.append("**Пункты и решения:**")
        for ch in charges:
            line = f"• {ch.get('ChargeCode','')} {ch.get('Description','')}".strip()
            if ch.get("Sentence"):
                line += f" — {ch['Sentence']}"
            L.append(line)
    if c.get("sentence"):
        L.append(f"**Наказание:** {c['sentence']}")
    parts = []
    if c.get("judge"): parts.append(f"судья {c['judge']}")
    if c.get("prosecutor"): parts.append(f"обвинитель {c['prosecutor']}")
    if c.get("defense"): parts.append(f"защита {c['defense']}")
    if parts:
        L.append("**Суд:** " + " · ".join(parts))
    L.append(f"*Подано: {c.get('filed_fmt') or '—'}*")
    return "\n".join(L)


def build_shift_markdown(s):
    """Готовый рапорт смены для вставки в Discord."""
    L = []
    L.append(f"🕓 **Рапорт смены #{s['id']} — {s.get('type_ru') or '—'}**")
    L.append(f"**Офицер:** {s.get('callsign') or '—'}" + (f" ({s['officer_name']})" if s.get("officer_name") else ""))
    L.append(f"**Длительность:** {s.get('duration_h') or '—'}")
    L.append(f"**Задержаний:** {s.get('arrests') or 0}")
    L.append(f"**Остановок транспорта:** {s.get('traffic_stops') or 0}")
    L.append(f"**Погонь:** {s.get('pursuits') or 0} · **PIT-манёвров:** {s.get('pit') or 0}")
    L.append(f"**Вызовов обработано:** {s.get('callouts') or 0}")
    L.append(f"**Штрафов на сумму:** ${s.get('fines_total') or 0}")
    L.append(f"*Начало смены: {s.get('started_fmt') or ''}*")
    return "\n".join(L)


def _clean_charge(text):
    """'VC.2800.1 · Уклонение (Misdemeanor)' → 'VC.2800.1 Уклонение'."""
    if not text:
        return ""
    t = text.replace("·", " ")
    # убрать класс в скобках в конце
    if "(" in t and t.rstrip().endswith(")"):
        t = t[:t.rfind("(")]
    return " ".join(t.split())


def _feed_time(record):
    """Время в формате ДД/ММ/ГГГГ ЧЧ:ММ."""
    import datetime
    raw = (record.get("game_time") or record.get("issued_at")
           or record.get("created_fmt") or record.get("issued_fmt") or "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.datetime.strptime(raw[:19], fmt).strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            continue
    return raw


def build_feed(record, kind):
    """Лента событий в фиксированном формате:
       <событие>
       <офицер>
       <нарушитель>
       <место>
       Статьи: <код описание>
       <дата время>
    """
    event = {"arrest": "Произошло задержание", "citation": "Выдан штраф",
             "warning": "Вынесено предупреждение"}.get(kind, "Событие")
    officer = record.get("officer_name") or record.get("callsign") or "—"
    who = record.get("suspect_name") or record.get("subject_name") or "—"
    where = record.get("zone") or record.get("location") or "—"

    lines = [event, officer, who, where]
    if kind == "warning":
        lines.append("Причина: " + (record.get("reason") or "—"))
    else:
        charges = [_clean_charge(c) for c in (record.get("charges") or []) if _clean_charge(c)]
        if charges:
            lines.append("Статьи: " + charges[0])
            lines.extend(charges[1:])
        else:
            lines.append("Статьи: —")
    lines.append(_feed_time(record))
    return "\n".join(lines)


def send_feed(record, kind, webhook=None):
    """Отправить событие в ленту Discord. (ok, message)."""
    url = webhook or config.DISCORD_WEBHOOK_URL
    if not url:
        return False, "Webhook не задан"
    try:
        r = requests.post(url, json={"content": build_feed(record, kind)}, timeout=15)
        if r.status_code in (200, 204):
            return True, "отправлено в ленту"
        return False, f"Discord вернул {r.status_code}"
    except Exception as e:
        return False, f"ошибка: {e}"


def send_case(case):
    """Возвращает (ok, message). Скрин прикладывается файлом, если есть на диске."""
    if not config.DISCORD_WEBHOOK_URL:
        return False, "Webhook не задан (DISCORD_WEBHOOK_URL). Карточка не отправлена."

    embed = build_embed(case)
    payload = {"embeds": [embed]}

    shot = case.get("screenshot")
    shot_path = os.path.join(config.SCREENSHOT_DIR, shot) if shot else None

    try:
        if shot_path and os.path.exists(shot_path):
            # embed + вложение-скриншот
            embed["image"] = {"url": f"attachment://{os.path.basename(shot_path)}"}
            with open(shot_path, "rb") as f:
                files = {"file": (os.path.basename(shot_path), f, "image/png")}
                r = requests.post(config.DISCORD_WEBHOOK_URL,
                                  data={"payload_json": _json(payload)}, files=files, timeout=15)
        else:
            r = requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=15)
        if r.status_code in (200, 204):
            db.mark_discord_sent(case["id"])
            return True, "Карточка отправлена в Discord."
        return False, f"Discord вернул {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"Ошибка отправки: {e}"


def _json(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)
