# Бэкенд-«мозг» — детальная спецификация

**Назначение:** полный чертёж бэкенда до кода. Включает ТОЧНЫЙ wire-протокол Gemini Live (извлечён из декомпила клиента конкурента), схемы данных, структуру модулей.
**Язык:** Python 3.11, FastAPI + `websockets`.

---

## 1. Структура проекта

```
backend/
  main.py                  — FastAPI app, WebSocket endpoint /dispatch
  config.py                — env/ini: BRAIN=gemini|local, ключи, хост, модель
  gateway/
    session.py             — DispatchSession: один игрок = одна сессия
    protocol.py            — схемы сообщений игра⇆бэкенд (pydantic)
  brain/
    base.py                — IBrain / BrainSession (абстракция)
    gemini_brain.py        — GeminiBrain (Live API, точный протокол — см. §4)
    local_brain.py         — LocalBrain (Whisper→LLM→TTS, Фаза 3)
  dispatch/
    tools.py               — парсер токенов ИмяКоманды{...} → structured
    context.py             — сбор/форматирование GameContext в промпт-блок
    memory.py              — ShiftMemory (событийный лог + сводка)
    personas.py            — пул персонажей + ротация
    prompt.py              — сборка system instruction из блоков
  voice/
    gate.py                — VAD (Silero/webrtcvad): режем тишину
  requirements.txt
```

---

## 2. Схемы сообщений (игра ⇆ бэкенд)

WebSocket: текстовые кадры = JSON, бинарные кадры = сырой PCM16 16кГц.

### Клиент → Бэкенд

```jsonc
// hello (первое сообщение)
{ "type":"hello", "auth":"<token>", "game":"lspdfr",
  "persona_pref":"random", "sample_rate":16000 }

// ptt
{ "type":"ptt", "state":"down" }   // down | up

// context (по изменению состояния игры)
{ "type":"context", "data": { /* GameContext, см. §3 */ } }

// tool_result (ответ на PlateRun/NameRun)
{ "type":"tool_result", "id":"<callId>", "tool":"NameRun",
  "result": { "wanted":true, "license":"Suspended", "citations":3 } }

// (бинарный кадр) — PCM16 16кГц, пока PTT down
```

### Бэкенд → Клиент

```jsonc
{ "type":"ready", "persona":"Михаил", "callsign":"2-Adam-12" }

// (бинарный кадр) — PCM голоса диспетчера (24кГц у Gemini out; ресемпл при нужде)

{ "type":"tool_call", "id":"c17", "tool":"RequestBackup",
  "args": { "units":2, "code":3 } }

{ "type":"transcript", "role":"dispatcher", "text":"...приято, высылаю..." }

{ "type":"error", "code":"brain_disconnect", "message":"..." }
```

---

## 3. Схема GameContext

```jsonc
{
  "agency": "lspd",              // GetCurrentAgencyScriptName()
  "callsign": "2-Adam-12",       // генерится на сессию
  "zone": "Vinewood Hills",      // GetZoneAtPosition().RealAreaName
  "county": "LosSantos",         // WorldZone.County
  "postal": "1234",              // из CDF (опц., может отсутствовать)
  "on_duty": true,
  "active_callout": null,        // GetCurrentCallout()/IsCalloutRunning()
  "in_pursuit": false,           // GetActivePursuit()!=null
  "time_of_day": "23:40"
}
```

Форматируется в блок «ТЕКУЩАЯ ОБСТАНОВКА» промпта (блок 9 v1) и обновляется в сессии Gemini через `clientContent` (см. §4.5).

---

## 4. GeminiBrain — ТОЧНЫЙ протокол Live API

> Извлечено из декомпилированного `GeminiLiveClient` конкурента. Можно реализовать дословно.

### 4.1. Подключение
```
wss://{host}/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={API_KEY}
```
- `{host}` для прямого Google = `generativelanguage.googleapis.com`.
  (Конкурент проксирует через свой `gemini.vinewood-hub.com` — нам прокси не нужен, ходим прямо.)
- `{API_KEY}` — ключ Google AI Studio (free-tier на старте).

### 4.2. Setup (первое сообщение после коннекта)
```jsonc
{ "setup": {
    "model": "models/gemini-3.1-flash-live-preview",
    "generationConfig": {
      "responseModalities": ["AUDIO"],
      "maxOutputTokens": 512,
      "thinkingConfig": { "thinkingBudget": 0 },        // 0 = без «раздумий», меньше задержка
      "speechConfig": { "voiceConfig": {
        "prebuiltVoiceConfig": { "voiceName": "Charon" } // голос персонажа
      }}
    },
    "systemInstruction": { "parts": [ { "text": "<ВЕСЬ СИСТЕМНЫЙ ПРОМПТ>" } ] },
    "tools": [],                                          // можно оставить пустым (команды парсим из текста)
    "inputAudioTranscription": {},                        // включает транскрипт входа
    "outputAudioTranscription": {},                       // включает транскрипт выхода (для subtitles/логов)
    "sessionResumption": {}                               // для переподключения
}}
```
Ждём ответ с `"setupComplete"`.

### 4.3. Отправка аудио (микрофон офицера)
```jsonc
{ "realtimeInput": { "audio": {
    "mimeType": "audio/pcm;rate=16000",
    "data": "<base64 PCM16>" } } }
```
Разбивай на чанки (~каждые N мс). После отпускания PTT:
```jsonc
{ "realtimeInput": { "audioStreamEnd": true } }
```

### 4.4. Приём (голос диспетчера)
- Сообщения с `"serverContent"`, внутри `"inlineData"` → base64 PCM голоса (обычно 24кГц) → проиграть.
- Конец реплики: `"turnComplete": true`.
- Транскрипт — в полях inputTranscription/outputTranscription (если включены).

### 4.5. Инъекция контекста/памяти (без голоса)
Отправка текста в сессию (напр. обновление обстановки, результат пробива):
```jsonc
{ "clientContent": {
    "turns": [ { "role":"user", "parts":[ { "text":"[CONTEXT: район сменился на Sandy Shores]" } ] } ],
    "turnComplete": true } }
```
> Конкурент так же вставляет `[PR_CONTEXT: ...]`. Мы тем же каналом шлём GameContext-апдейты и `tool_result`.

### 4.6. Fallback-TTS (отдельный REST, опц.)
Если нужен разовый синтез фразы вне Live-сессии:
```
POST https://{host}/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={KEY}
body: {"contents":[{"parts":[{"text":"..."}]}],
       "generationConfig":{"responseModalities":["AUDIO"],
         "speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Charon"}}}}}
```

---

## 5. Парсер команд (dispatch/tools.py)

```
Регулярка (из декомпила конкурента):
  ([A-Za-z_]{3,})\s*[\{\(]([^\}\)]*)[\}\)]

Алгоритм:
1. Из текстовой части ответа LLM (или из outputTranscription) выдёргиваем токены.
2. Валидируем имя по каталогу (COMMAND-CATALOG.md). Неизвестное — игнор + лог.
3. Парсим аргументы (key:value, через запятую).
4. Эмитим {type:"tool_call", id, tool, args} клиенту.
5. Текст токена вырезаем из того, что идёт в озвучку (в Live модель сама не произносит
   токен, но на всякий случай чистим транскрипт для субтитров).
```

---

## 6. ShiftMemory (dispatch/memory.py)

```
Событие: { ts, type, zone, summary }
  типы: shift_start, callout, traffic_stop, pursuit, plate_run, name_run, code4, note

Хранение: список в памяти сессии (+ опц. JSON-дамп на диск для «непрерывной службы»).

Сводка в промпт (блок 8/F):
  - последние 8 событий дословно (краткие строки)
  - старше — одной строкой-саммари («за смену: 3 остановки, 1 погоня в Виновуде»)

Инъекция: при заметных событиях обновляем {{SHIFT_MEMORY}} через clientContent (§4.5),
не чаще раза в N секунд, чтобы не спамить контекст.
```

---

## 7. Конфиг бэкенда (config)

```ini
BRAIN=gemini                 # gemini | local
GEMINI_API_KEY=...           # из Google AI Studio (free tier)
GEMINI_MODEL=gemini-3.1-flash-live-preview
GEMINI_HOST=generativelanguage.googleapis.com
MAX_OUTPUT_TOKENS=512
VAD=silero                   # silero | webrtc | off
AUTH_TOKENS=token1,token2    # простая авторизация клиентов
```

---

## 8. Поток одной сессии (сводка)

```
1. Клиент → hello → бэкенд создаёт DispatchSession, выбирает персонажа, callsign.
2. Бэкенд собирает system prompt (prompt.py: блоки + persona + memory + context).
3. IBrain.start_session → GeminiBrain коннектится, шлёт setup (§4.2).
4. Бэкенд → ready.
5. PTT down → клиент шлёт PCM-чанки → VAD-гейт → GeminiBrain.send_audio (§4.3).
6. PTT up → audioStreamEnd (§4.3).
7. Gemini → serverContent/inlineData → бэкенд → бинарный PCM клиенту (проиграть).
8. Из транскрипта/текста → tools.py парсит токены → tool_call клиенту.
9. Клиент исполняет, при PlateRun/NameRun → tool_result → бэкенд → clientContent (§4.5)
   → диспетчер зачитывает результат.
10. context-апдейты и memory — тем же clientContent-каналом.
```

---

## 9. Заметки по имплементации

- **Ресемплинг:** вход 16кГц (Gemini требует), выход у Gemini обычно 24кГц — на клиенте
  проигрывать как есть или ресемплить под устройство.
- **Задержка:** `thinkingBudget:0` обязателен для realtime. Бэкенд-хоп добавляет мс —
  на проде разместить бэкенд ближе к региону Gemini.
- **Реконнект:** хранить `sessionResumption` handle, при обрыве переподключаться и
  восстанавливать сессию (конкурент делает так же — `BuildResumptionField()`).
- **Команды через текст, не Gemini-tools:** проще и надёжнее парсить токены из ответа,
  чем настраивать нативный function-calling Live API (конкурент выбрал текстовый путь).
```
