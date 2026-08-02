/**
 * LAPD Records — шлюз приёма данных (Cloudflare Worker).
 *
 * Зачем: чтобы GitHub-токен НЕ лежал в лаунчере. Лаунчер шлёт данные сюда,
 * а Worker уже своим секретным токеном кладёт их в inbox репозитория.
 * Даже если кто-то вскроет .exe — токена там нет.
 *
 * Секреты (задаются в панели Cloudflare, НЕ в коде):
 *   GITHUB_TOKEN — fine-grained токен с правом Contents:write на репозиторий
 *   GITHUB_REPO  — например "osminoog09-star/dispatch-one-records"
 *   SHARED_KEY   — простой пароль, который знает лаунчер (защита от чужих запросов)
 */

const RATE = new Map(); // простая защита от флуда: позывной -> время последнего запроса

export default {
  async fetch(request, env) {
    // CORS / метод
    if (request.method === "OPTIONS") {
      return cors(new Response(null, { status: 204 }));
    }

    // ВРЕМЕННАЯ ДИАГНОСТИКА: GET ?debug=1 показывает, что видит Worker (без раскрытия секретов)
    const url = new URL(request.url);
    if (request.method === "GET" && url.searchParams.get("debug") === "1") {
      const t = env.GITHUB_TOKEN || env.GITHUB_TOKE || "";
      // Worker сам делает GET к GitHub тем же токеном — увидим точный ответ
      let ghStatus = "?", ghMsg = "";
      try {
        const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}`, {
          headers: {
            Authorization: `Bearer ${t}`,
            Accept: "application/vnd.github+json",
            "User-Agent": "lapd-records-gateway",
          },
        });
        ghStatus = r.status;
        const jd = await r.json();
        ghMsg = jd.message || jd.full_name || "";
      } catch (e) {
        ghMsg = "fetch err: " + e;
      }
      return cors(json({
        repo: env.GITHUB_REPO || "(нет)",
        token_len: t.length,
        github_status: ghStatus,
        github_msg: ghMsg,
      }));
    }
    if (request.method !== "POST") {
      return cors(json({ error: "only POST" }, 405));
    }

    // проверка общего ключа
    const key = request.headers.get("X-Client-Key") || "";
    if (!env.SHARED_KEY || key !== env.SHARED_KEY) {
      return cors(json({ error: "bad key" }, 401));
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return cors(json({ error: "bad json" }, 400));
    }

    const profile = body.profile || {};
    const callsign = (profile.callsign || "").trim();
    if (!callsign) {
      return cors(json({ error: "no callsign" }, 400));
    }

    // анти-флуд: не чаще раза в 10 секунд с одного позывного
    const now = Date.now();
    const last = RATE.get(callsign) || 0;
    if (now - last < 10000) {
      return cors(json({ error: "too fast" }, 429));
    }
    RATE.set(callsign, now);

    // есть ли что отправлять
    const hasData = ["arrests", "citations", "cases", "shifts", "warnings"]
      .some((k) => Array.isArray(body[k]) && body[k].length);
    if (!hasData) {
      return cors(json({ ok: true, msg: "новых данных нет" }));
    }

    // кладём в inbox репозитория через GitHub API (токен — секрет Worker'а)
    const safe = callsign.replace(/[^a-zA-Z0-9_-]/g, "");
    const path = `server/inbox/${safe}-${Math.floor(now / 1000)}.json`;
    const content = toBase64(JSON.stringify(body, null, 1));

    const token = env.GITHUB_TOKEN || env.GITHUB_TOKE;  // терпим опечатку в имени секрета
    const gh = await fetch(
      `https://api.github.com/repos/${env.GITHUB_REPO}/contents/${path}`,
      {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "lapd-records-gateway",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: `Данные офицера ${callsign} (через шлюз)`,
          content,
        }),
      }
    );

    if (gh.status === 200 || gh.status === 201) {
      return cors(json({ ok: true, msg: "принято" }));
    }
    const detail = await gh.text();
    return cors(json({ error: `github ${gh.status}`, detail: detail.slice(0, 200) }, 502));
  },
};

function toBase64(str) {
  // UTF-8 → base64 без unescape (которого нет в среде Workers)
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function cors(resp) {
  resp.headers.set("Access-Control-Allow-Origin", "*");
  resp.headers.set("Access-Control-Allow-Headers", "Content-Type, X-Client-Key");
  resp.headers.set("Access-Control-Allow-Methods", "POST, OPTIONS");
  return resp;
}
