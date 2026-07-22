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
    fields = [
        {"name": "Подозреваемый", "value": case.get("suspect_name") or "Неизвестный", "inline": True},
        {"name": "Статус розыска", "value": "🔴 В розыске" if wanted else "🟢 Чисто", "inline": True},
        {"name": "Права", "value": case.get("license_ru") or "—", "inline": True},
        {"name": "Район", "value": case.get("zone") or "—", "inline": True},
        {"name": "Индекс", "value": case.get("postal") or "—", "inline": True},
        {"name": "Штрафы", "value": str(case.get("citations") or 0), "inline": True},
        {"name": "Офицер", "value": case.get("callsign") or "—", "inline": True},
        {"name": "Время", "value": case.get("game_time") or case.get("created_at") or "—", "inline": True},
        {"name": "Статус дела", "value": case.get("status_ru") or "—", "inline": True},
    ]
    embed = {
        "title": f"Рапорт о задержании · Дело #{case['id']}",
        "color": COLOR_WANTED if wanted else COLOR_NORMAL,
        "fields": fields,
        "footer": {"text": f"{config.COMMUNITY_NAME} · Dispatch One Records"},
    }
    return embed


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
