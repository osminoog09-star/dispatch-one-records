"""
Отправка данных игрока напрямую в GitHub — без хостинга и без сервера.

Агент кладёт файл в папку inbox репозитория через GitHub API.
Дальше GitHub Actions сам принимает его и пересобирает сайт (даже если ПК владельца выключен).

Настройки в sync-config.ini:
    UPLOAD_MODE=github
    GITHUB_REPO=osminoog09-star/dispatch-one-records
    GITHUB_TOKEN=<токен сообщества, выдаёт админ>
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request


def _api(url, token, method="GET", payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "dispatch-one-agent")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "ignore")[:300]}


def upload_records(repo, token, profile, arrests, citations, cases):
    """Кладёт данные игрока в inbox репозитория. Возвращает (ok, сообщение)."""
    if not repo or not token:
        return False, "не заданы GITHUB_REPO / GITHUB_TOKEN"

    payload = {
        "profile": profile,
        "arrests": arrests or [],
        "citations": citations or [],
        "cases": cases or [],
        "sent_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if not (payload["arrests"] or payload["citations"] or payload["cases"]):
        return True, "новых данных нет"

    safe_cs = "".join(ch for ch in (profile.get("callsign") or "unknown")
                      if ch.isalnum() or ch in "-_")
    path = f"server/inbox/{safe_cs}-{int(time.time())}.json"
    content = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
    ).decode("ascii")

    status, body = _api(
        f"https://api.github.com/repos/{repo}/contents/{path}", token, "PUT",
        {"message": f"Данные офицера {profile.get('callsign')}", "content": content},
    )
    if status in (200, 201):
        return True, f"отправлено ({len(payload['arrests'])} задерж., " \
                     f"{len(payload['citations'])} штраф., {len(payload['cases'])} суд.)"
    return False, f"GitHub вернул {status}: {str(body)[:160]}"
