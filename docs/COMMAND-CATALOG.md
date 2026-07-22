# Каталог команд диспетчера + точные сигнатуры LSPDFR

**Назначение:** полный список команд-токенов, которые выдаёт LLM, и их точный маппинг на API LSPDFR.
**Сигнатуры:** извлечены рефлексией (Mono.Cecil) из `LSPD First Response.dll` — без запуска игры.
**Обозначения:** ✅ Фаза 1 (стартовый набор) · 🔷 Фаза 2 · ⚙️ требует внешний мод.

---

## Часть 1. Команды-токены (что видит LLM)

Формат в ответе LLM: `ИмяКоманды{ключ:значение, ключ:значение}`. Токен не произносится вслух.

| # | Команда | Аргументы | Фаза | Действие |
|---|---|---|---|---|
| 1 | `RequestBackup` | `units:int, code:int(1-3), unit:str` | ✅ | Вызов подкрепления |
| 2 | `PursuitBackup` | `code:int` | ✅ | Подкрепление в погоню |
| 3 | `StatusCheck` | `status:"10-8"/"10-7"` | ✅ | Смена доступности экипажа |
| 4 | `DispatchCallout` | `type:str` | ✅ | Выдать игроку вызов |
| 5 | `PlateRun` | `plate:str` | ✅ | Пробить автономер (результат → назад) |
| 6 | `NameRun` | `name:str` | ✅ | Пробить личность (результат → назад) |
| 7 | `Advisory` | `text:str` | ✅ | Сообщение по рации, без действия |
| 8 | `AirSupport` | — | 🔷 | Вертолёт |
| 9 | `Canine` | — | 🔷 | Кинолог K9 |
| 10 | `SpikeStrips` | — | 🔷 | Шипы |
| 11 | `EMS` | — | 🔷 | Скорая |
| 12 | `Fire` | — | 🔷 | Пожарные |
| 13 | `Coroner` | — | 🔷 | Коронер |
| 14 | `Bolo` | `text:str` | 🔷 | Ориентировка |
| 15 | `SwatTeam` | `code:int` | 🔷 | Спецназ |
| 16 | `PrisonerTransport` | — | 🔷 | Транспорт для задержанного |
| 17 | `AuthorizePursuit` | — | 🔷 | Санкция на погоню |
| 18 | `EndPursuit` | — | 🔷 | Прекратить погоню |
| 19 | `DismissUnits` | — | 🔷 | Отпустить экипажи |
| 20 | `TrafficStopBackup` | `code:int` | 🔷 | Подкрепление на остановку |

---

## Часть 2. Маппинг на LSPDFR API (точные сигнатуры)

Namespace: `LSPD_First_Response.Mod.API.Functions` (статический класс).
Позиция берётся как `Game.LocalPlayer.Character.Position` (Vector3).

### 1. RequestBackup ✅

```csharp
// Точные перегрузки:
Vehicle RequestBackup(Vector3 position, EBackupResponseType responseType, EBackupUnitType backupUnitType)
Vehicle RequestBackup(Vector3 position, EBackupResponseType responseType, EBackupUnitType backupUnitType, string agencyScriptName)
Vehicle RequestBackup(Vector3 position, EBackupResponseType responseType, EBackupUnitType backupUnitType, string agencyScriptName, bool exactLocation, bool noResponseTask)
```

**Enum `EBackupResponseType`:** `Code2=0`, `Code3=1`, `Pursuit=2`, `SuspectTransporter=3`
**Enum `EBackupUnitType`:** `LocalUnit=0`, `StateUnit=1`, `SwatTeam=2`, `NooseTeam=3`, `AirUnit=4`, `NooseAirUnit=5`, `Ambulance=6`, `Firetruck=7`, `PrisonerTransport=8`

**Маппинг токена → вызов:**
```
RequestBackup{units:2, code:3}
  → response = (code==3 ? Code3 : Code2)
  → for i in 1..units: Functions.RequestBackup(pos, response, EBackupUnitType.LocalUnit)

RequestBackup{unit:"state"} → EBackupUnitType.StateUnit
PursuitBackup{code:3}       → Functions.RequestBackup(pos, EBackupResponseType.Pursuit, LocalUnit)
```

### 2. Погоня 🔷

```csharp
LHandle GetActivePursuit()
LHandle CreatePursuit()
void    ForceEndPursuit(LHandle pursuit)
void    SetPursuitAsCalledIn(LHandle pursuit, bool calledIn)
bool    IsPursuitStillRunning(LHandle pursuit)
void    AddPedToPursuit(LHandle pursuit, Ped ped)
```
```
AuthorizePursuit{} → var p = GetActivePursuit(); if (p!=null) SetPursuitAsCalledIn(p, true)
EndPursuit{}       → var p = GetActivePursuit(); if (p!=null) ForceEndPursuit(p)
```

### 3. StatusCheck ✅

```csharp
void SetPlayerAvailableForCalls(bool value)
bool IsPlayerAvailableForCalls()
```
```
StatusCheck{status:"10-8"} → SetPlayerAvailableForCalls(true)   // на службе
StatusCheck{status:"10-7"} → SetPlayerAvailableForCalls(false)  // вне службы
```

### 4. DispatchCallout ✅

```csharp
void   StartCallout(string name)
void   StopCurrentCallout()
bool   IsCalloutRunning()
LHandle GetCurrentCallout()
string GetCalloutFriendlyName(LHandle callout)
void   AcceptPendingCallout(LHandle callout)
```
```
DispatchCallout{type:"TrafficStop"} → if(!IsCalloutRunning()) StartCallout("TrafficStop")
```
> Имена вызовов зависят от установленных callout-паков. Держим маппинг «человеческий тип → имя callout».

### 5. PlateRun / NameRun ✅ (двусторонние)

> В ядре LSPDFR прямого «пробить номер» нет — данные лица берутся из `Persona` остановленного Ped, а БД-ответ формируем сами.

**Persona (класс `...Engine.Scripting.Entities.Persona`), поля для ответа:**
```csharp
string Forename, Surname, FullName
Gender Gender
DateTime Birthday
bool   Wanted                 // в розыске
ELicenseState ELicenseState   // None=0, Unlicensed=1, Expired=2, Valid=3, Suspended=4
int    Citations              // штрафы
int    TimesStopped           // сколько раз останавливали
WantedInformation WantedInformation
```
**Поток:**
```
NameRun{name:"..."}  → взять Persona ближайшего/остановленного Ped (PersonaHelper)
                     → сформировать result:
                        { wanted: Persona.Wanted,
                          license: Persona.ELicenseState,  // Valid/Suspended/Expired/...
                          citations: Persona.Citations }
                     → отправить tool_result → LLM зачитывает по рации

PlateRun{plate:"..."} → аналогично по владельцу авто (Persona водителя),
                        + статус авто (в угоне/застраховано) генерим или из мода.
```

### 6. Контекст (для GameContext, не команды)

```csharp
string    GetCurrentAgencyScriptName()          // "lspd"/"bcso"/"sahp"
WorldZone GetZoneAtPosition(Vector3 position)   // .RealAreaName, .County, .GameName
bool      IsCalloutRunning()
LHandle   GetActivePursuit()                     // != null → идёт погоня
```
**WorldZone поля:** `RealAreaName` (человеческое имя района), `County` (EWorldZoneCounty), `GameName`, `CallPrefix`.

### 7. Скан-аудио (озвучка через игровой сканнер, опц.)

```csharp
void PlayScannerAudio(string sound)
void PlayScannerAudio(string sound, bool shortIntro)
void PlayScannerAudioUsingPosition(string sound, Vector3 position)
```

### 8. События (подписки в EntryPoint)

```csharp
Functions.OnOnDutyStateChanged += handler;   // вышел/сошёл со смены
Functions.PlayerWentOnDutyFinishedSelection += handler;
```

---

## Часть 3. Внешние зависимости (не ядро LSPDFR) ⚙️

| Нужно | Где брать | Примечание |
|---|---|---|
| `GetPostalCode(pos)` | **CommonDataFramework** / PostalCodeProvider | В ядре LSPDFR нет; конкурент тоже тянет из внешнего мода. Через рефлексию по загруженной сборке. |
| Статус доступности «Grammar Police» | GrammarPolice.dll | Опц., у конкурента StatusCheck сначала пробует его. |
| Расширенный пробив/БД | CommonDataFramework | Богаче Persona (машины, судимости). |

> Приём доступа: рефлексия по загруженным сборкам в рантайме (как в [[autotrader-reflect-dll-signatures]]) — берём типы `ImmersiveAmbientEvents`, `PolicingRedefined`, CDF по имени, без жёсткой зависимости на этапе компиляции. Так конкурент и делает.

---

## Часть 4. Резюме — что готово к коду Фазы 1

Стартовый набор (7 команд) полностью покрыт точными сигнатурами:
`RequestBackup`, `PursuitBackup`, `StatusCheck`, `DispatchCallout`, `PlateRun`, `NameRun`, `Advisory`.
Контекст (агентство, район, погоня, вызов) — тоже. Единственная внешняя зависимость для контекста — почтовый индекс (CDF), и она опциональна (можно временно слать район без индекса).
```
