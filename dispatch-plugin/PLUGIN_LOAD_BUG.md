# ИСПРАВЛЕНО: плагин DispatchOne.MDT не загружался в игре

Диагностировал и починил: Claude, 2026-08-07, по логу игрока 3-LINCOLN-17 (тикет поддержки).

## СТАТУС: FIXED (пересобран DLL, проверено метаданными; в игре не тестировалось)
- `dispatch-plugin/DispatchOneMdt.cs`: база класса сменена `Rage.Plugin` →
  `LSPD_First_Response.Mod.API.Plugin`; добавлен `[assembly: Rage.Attributes.Plugin(...)]`.
- `dispatch-plugin/stub/RageStub.cs`: добавлен стаб `Rage.Attributes.PluginAttribute`.
- Пересобран `dispatch-plugin/out/DispatchOne.MDT.dll`; скопирован в
  `launcher/DispatchOne.MDT.dll` и в onedir-dist `_internal/` (md5 совпадают).
- Проверено Cecil: тип `DispatchOne.DispatchOneMdt : LSPD_First_Response.Mod.API.Plugin`
  (реальная LSPDFR-сборка), атрибут сборки на месте, `Initialize/Finally` — override.
- ОСТАЛОСЬ (доставка игрокам): пересобрать релизный лаунчер (onedir), чтобы вшитый
  `DispatchOne.MDT.dll` попал в новый exe/дистрибутив, и выложить release asset.
  Исходная вшиваемая копия `launcher/DispatchOne.MDT.dll` уже обновлена — следующая
  сборка лаунчера подхватит фикс автоматически.

---
## Исходный баг-репорт (для истории)

## Симптом (у игроков)
- Тикеты: «не отправляются данные на сайт», «агент запускается, но ничего не делает»,
  «ошибка подключение не установлено».
- В `RagePluginHook.log`:
  - `Unable to load one or more of the requested types` при `Assembly.GetTypes()`
    (LSPDFR CalloutManager сканирует плагины).
  - `Не удалось загрузить тип "DispatchOne.DispatchOneMdt" из сборки "DispatchOne.MDT …",
    так как родитель имеет тип Sealed.`
  - `CalloutInterface: [ERROR] there was an error while trying to access plugin: DispatchOne.MDT`.

## Причина
`dispatch-plugin/DispatchOneMdt.cs:20`:
```csharp
public class DispatchOneMdt : Rage.Plugin
```
В реальном RagePluginHook класс `Rage.Plugin` — **`sealed`**, от него НЕЛЬЗЯ наследоваться,
поэтому тип не создаётся и весь плагин не грузится. Наш стаб
`dispatch-plugin/stub/*.cs:9` объявляет `Rage.Plugin` как `abstract` — поэтому оно
компилируется у нас, но падает в игре. Рассинхрон стаба и реального API.

Важно: базовые аресты/штрафы всё равно доходят на сайт через pdComp → агент
(`pdcomp_sync.exe` читает JSON pdComp напрямую). Но in-game MDT-функции плагина
(живые проверки ped/plate через CalloutInterface) НЕ работают ни у кого, пока это не починено.

## Что сделать (Codex)
1. Убрать наследование от `Rage.Plugin`. Современный паттерн RPH — атрибут сборки + точка входа,
   без базового класса, например:
   ```csharp
   [assembly: Rage.Attributes.Plugin("DispatchOne MDT", Description="...", Author="LAPD Records")]
   ```
   и `public static void Main()` / `Initialize()` как entry point; либо реализовать актуальный
   интерфейс плагина RPH (не `Rage.Plugin`).
2. Привести стаб `dispatch-plugin/stub` в соответствие с реальным API (убрать/пометить `Plugin`
   как `sealed`, добавить `Rage.Attributes.PluginAttribute` и т.п.), чтобы стаб отражал реальность
   и такой баг ловился на компиляции.
3. Пересобрать `DispatchOne.MDT.dll` (`dispatch-plugin/build.ps1`), проверить, что LSPDFR грузит
   плагин без TypeLoadException (в чистом логе не должно быть «родитель имеет тип Sealed»).
4. Обновить вшитый DLL в лаунчере (`launcher/DispatchOne.MDT.dll`) и в агенте, перевыпустить.

## Проверка после фикса
- В `RagePluginHook.log` при загрузке есть строка вида `[DispatchOne] Loaded.` и НЕТ
  `Unable to load one or more of the requested types` / `родитель имеет тип Sealed` для нашей сборки.
- CalloutInterface больше не пишет ERROR по `DispatchOne.MDT`.
