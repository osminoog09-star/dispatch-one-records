# Каркас репозитория — готово к коду

**Назначение:** точная структура файлов, зависимости и конфиги обеих частей, чтобы код стартовал без раздумий.

---

## Общая структура

```
AIDispatcher/
  docs/                     — вся бумага (этот и соседние документы)
  backend/                  — Python «мозг» (см. BACKEND-SPEC.md §1)
  clients/
    lspdfr/                 — C# плагин (Фаза 1)
    fivem/                  — FiveM ресурс (Фаза 2)
  shared/
    protocol.md             — единый протокол сообщений (ссылка на BACKEND-SPEC §2)
  README.md
```

---

## Часть 1. Backend (Python)

### requirements.txt
```
fastapi>=0.110
uvicorn[standard]>=0.29
websockets>=12.0
pydantic>=2.6
google-genai>=0.3         # опц.: официальный SDK; или сырой websockets по BACKEND-SPEC §4
numpy>=1.26               # аудио-буферы/ресемпл
silero-vad                # VAD-гейт (или webrtcvad)
python-dotenv>=1.0
```
> На старте можно БЕЗ google-genai — общаться с Live API сырым `websockets` по точному
> протоколу из BACKEND-SPEC §4. Меньше «магии», полный контроль.

### Запуск (локально, бесплатно)
```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
set GEMINI_API_KEY=...        # free-tier из AI Studio
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```
Клиент подключается на `ws://localhost:8080/dispatch`.

---

## Часть 2. LSPDFR-клиент (C# .NET Framework 4.8)

### Структура (см. TECH-DESIGN §3.1)
```
clients/lspdfr/
  AIDispatcher.LSPDFR.csproj
  EntryPoint.cs
  Config.cs
  Audio/MicCapture.cs
  Audio/VoicePlayer.cs
  Net/BackendClient.cs
  Game/ContextProvider.cs
  Game/ToolExecutor.cs
  AIDispatcher.ini            — конфиг (см. TECH-DESIGN §3.5)
```

### .csproj — ключевые ссылки
```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net48</TargetFramework>
    <LangVersion>latest</LangVersion>
    <Platform>x64</Platform>
    <AssemblyName>AIDispatcher</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
    <!-- Ссылки на игровые/модовые DLL (Reference, НЕ копировать) -->
    <Reference Include="RagePluginHookAPI"><HintPath>libs\RagePluginHookAPI.dll</HintPath><Private>false</Private></Reference>
    <Reference Include="LSPD First Response"><HintPath>libs\LSPD First Response.dll</HintPath><Private>false</Private></Reference>
    <Reference Include="RAGENativeUI"><HintPath>libs\RAGENativeUI.dll</HintPath><Private>false</Private></Reference>
    <!-- Аудио + сеть (копировать в deps) -->
    <Reference Include="NAudio"><HintPath>libs\NAudio.dll</HintPath></Reference>
  </ItemGroup>
</Project>
```
> `libs\` — копии DLL из папки игры (RagePluginHookAPI, LSPD First Response, RAGENativeUI,
> NAudio*). WebSocket на клиенте — `System.Net.WebSockets.ClientWebSocket` (есть в net48).

### Точка входа (скелет)
```csharp
public class EntryPoint : Plugin      // RagePluginHook.Plugin
{
    public override void Initialize()
    {
        Functions.OnOnDutyStateChanged += OnDuty;   // подписка LSPDFR
        Game.LogTrivial("[AIDispatcher] loaded");
    }
    public override void Finally() { /* cleanup */ }

    private void OnDuty(bool onDuty)
    {
        if (onDuty) { /* start session: mic + backend ws + context loop */ }
        else        { /* stop session */ }
    }
}
```

### Куда кладётся собранный DLL
```
<GTA>\plugins\LSPDFR\AIDispatcher.dll   (+ deps в \Vinewood\deps аналогично конкуренту)
```

---

## Часть 3. Сборка и деплой (Фаза 1, локально)

```
1. backend: uvicorn на localhost:8080 (бесплатно, свой ПК).
2. клиент: сборка AIDispatcher.dll → в plugins\LSPDFR.
3. AIDispatcher.ini: Url=ws://localhost:8080/dispatch, PTTKey=RMenu.
4. запуск игры через RagePluginHook, выход на смену → сессия стартует.
```

---

## Часть 4. Git / гигиена

```
.gitignore:
  .venv/  __pycache__/  *.pyc
  bin/ obj/ libs/*.dll         # игровые DLL не коммитим (лицензии)
  *.ini с ключами → .ini.example вместо реального
  .env
```
> Игровые/модовые DLL и API-ключи — вне репозитория. В репо только наш код + примеры конфигов.
```
