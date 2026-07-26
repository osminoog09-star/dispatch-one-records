# Fixes officer callsign and name in game configs (requires admin rights).
param(
    [string]$Callsign = "7-WILLIAM-1",
    [string]$OfficerName = "Denis Sherman"
)

$ErrorActionPreference = "Continue"
$base = "C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy\plugins\LSPDFR"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Позывной: $Callsign" -ForegroundColor Cyan
Write-Host "  Имя офицера: $OfficerName" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Меняет значение ключа построчно (не трогая переносы строк)
function Set-IniKey {
    param([string]$Path, [string]$Key, [string]$Value, [string]$Section)

    if (-not (Test-Path $Path)) {
        Write-Host ("  skip " + (Split-Path $Path -Leaf) + " (нет файла)") -ForegroundColor DarkGray
        return 0
    }

    $file = Split-Path $Path -Leaf
    try {
        $lines = [System.IO.File]::ReadAllLines($Path)
        $out = New-Object System.Collections.Generic.List[string]
        $cur = ""
        $done = $false
        $skipNext = $false

        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]
            $trim = $line.Trim()

            # пропускаем осиротевшую строку (последствие старой ошибки)
            if ($skipNext) {
                $skipNext = $false
                if ($trim -eq $Value) { continue }
            }

            if ($trim -match '^\[(.+)\]$') {
                $cur = $matches[1]
                $out.Add($line)
                continue
            }

            $m = [regex]::Match($line, '^([^\S\r\n]*)([A-Za-z0-9_]+)([^\S\r\n]*=[^\S\r\n]*)(.*)$')
            if ($m.Success -and $m.Groups[2].Value -ieq $Key -and
                ([string]::IsNullOrEmpty($Section) -or $cur -ieq $Section)) {
                $sep = $m.Groups[3].Value
                if ($sep -notmatch '=[^\S\r\n]') { $sep = $sep.TrimEnd() + " " }
                $out.Add($m.Groups[1].Value + $m.Groups[2].Value + $sep + $Value)
                $done = $true
                $skipNext = $true
                continue
            }

            $out.Add($line)
        }

        # ключа нет — добавляем в нужную секцию (восстановление испорченного конфига)
        if (-not $done) {
            $rebuilt = New-Object System.Collections.Generic.List[string]
            $sec = ""
            $inserted = $false
            foreach ($l in $out) {
                $rebuilt.Add($l)
                $t2 = $l.Trim()
                if ($t2 -match '^\[(.+)\]$') {
                    $sec = $matches[1]
                    if (-not $inserted -and ($sec -ieq $Section -or [string]::IsNullOrEmpty($Section))) {
                        $rebuilt.Add($Key + " = " + $Value)
                        $inserted = $true
                        $done = $true
                    }
                }
            }
            if ($inserted) { $out = $rebuilt }
        }

        $nl = [string][char]13 + [string][char]10
        $newText = ($out -join $nl)
        $oldText = ($lines -join $nl)
        if ($newText -ne $oldText) {
            $enc = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($Path, $newText + $nl, $enc)
            Write-Host ("  OK   " + $file + " -> " + $Key + " = " + $Value) -ForegroundColor Green
            return 1
        }
        if ($done) {
            Write-Host ("  --   " + $file + " (" + $Key + " уже верный)") -ForegroundColor DarkGray
        } else {
            Write-Host ("  ??   " + $file + " (ключ " + $Key + " не найден)") -ForegroundColor Yellow
        }
        return 0
    } catch {
        Write-Host ("  FAIL " + $file + " : " + $_.Exception.Message) -ForegroundColor Red
        return -1
    }
}

$changed = 0
$changed += Set-IniKey -Path "$base\GrammarPolice\custom.ini" -Key "Callsign"    -Value $Callsign
$changed += Set-IniKey -Path "$base\CalloutInterface.ini"     -Key "MDTCallsign" -Value $Callsign
$changed += Set-IniKey -Path "$base\BlueLineScanner.ini"      -Key "VizLabel"    -Value $Callsign
$changed += Set-IniKey -Path "$base\pdComp\config.ini"        -Key "Callsign"    -Value $Callsign -Section "Officer"
$changed += Set-IniKey -Path "$base\pdComp\config.ini"        -Key "Name"        -Value $OfficerName -Section "Officer"

Write-Host ""
Write-Host "Проверка:" -ForegroundColor Cyan
$check = @(
    @{P="$base\GrammarPolice\custom.ini"; K="Callsign"},
    @{P="$base\CalloutInterface.ini";     K="MDTCallsign"},
    @{P="$base\BlueLineScanner.ini";      K="VizLabel"},
    @{P="$base\pdComp\config.ini";        K="Callsign"},
    @{P="$base\pdComp\config.ini";        K="Name"}
)
foreach ($c in $check) {
    if (Test-Path $c.P) {
        $pat = "^[^\S\r\n]*" + $c.K + "[^\S\r\n]*="
        $l = Select-String -Path $c.P -Pattern $pat | Select-Object -First 1
        if ($l) { Write-Host ("  " + (Split-Path $c.P -Leaf) + " : " + $l.Line.Trim()) }
    }
}

Write-Host ""
if ($changed -gt 0) {
    Write-Host "Готово! Перезапусти игру." -ForegroundColor Green
} elseif ($changed -lt 0) {
    Write-Host "Есть ошибки записи — нужны права администратора." -ForegroundColor Red
} else {
    Write-Host "Всё уже настроено." -ForegroundColor Yellow
}
Write-Host "ВАЖНО: после обновления сборки Vinewood запусти этот файл снова." -ForegroundColor Yellow
Write-Host ""
Read-Host "Нажми Enter для выхода"
