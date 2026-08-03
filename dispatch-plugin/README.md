# DispatchOne.MDT — плагин для живых данных из игры

Ловит то, чего **нет в файлах** pdComp (эти данные существуют только в момент игры):

| Событие в игре | Что пишем |
|---|---|
| Проверка человека (MDT / CalloutInterface `OnPedCheck`) | документ NPC: имя, дата рождения, пол, розыск, штат прав, штрафы |
| Проверка машины (`OnPlateCheck`) | транспорт: номер, марка, модель, цвет, класс, владелец, страховка, регистрация |
| Встал/сошёл со смены у диспетчера (`OnOnDutyStateChanged`) | старт/конец смены |

Данные пишутся построчно (JSONL) в `plugins\LSPDFR\DispatchOne\mdt.jsonl`.
Агент `pdcomp_sync` потом их читает и шлёт на сайт.

## Сборка
```
powershell -ExecutionPolicy Bypass -File build.ps1
```
Готовый файл: `out\DispatchOne.MDT.dll`. (`refs\RagePluginHook.dll` — только заглушка
для компиляции; в игру её НЕ копировать, там настоящая.)

## Установка
1. Скопировать **`out\DispatchOne.MDT.dll`** в
   `C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy\plugins\LSPDFR\`
   (рядом с CalloutInterface). НЕ копировать `RagePluginHook.dll` из `refs`.
2. Запустить игру через RagePluginHook, встать на смену LSPDFR.

## Проверка (первый запуск — 2 минуты)
1. Встань на смену у диспетчера.
2. Пробей любого NPC (MDT / CalloutInterface — проверка личности).
3. Пробей любой номер машины.
4. Выйди из игры.
5. Пришли мне файл `plugins\LSPDFR\DispatchOne\mdt.jsonl` и лог
   `RagePluginHook\RagePluginHook.log` (строки со словом `DispatchOne`).

По этим двум файлам я вижу: загрузился ли плагин, летят ли события, и какой
РЕАЛЬНЫЙ формат данных — после чего достраиваю приём на сайте уже точно, без гадания.

## Если не загрузился
В `RagePluginHook.log` не будет строки `[DispatchOne.MDT] Загружен`.
Тогда попробуй положить DLL в папку `Plugins\` (RPH, в корне игры) вместо
`plugins\LSPDFR\` — и пришли лог. Плагин пишет причину ошибки в лог.
