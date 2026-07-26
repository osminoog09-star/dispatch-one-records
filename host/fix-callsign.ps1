# Прописывает позывной и имя офицера во все игровые конфиги (нужны права администратора).
param(
    [string]$Callsign = "7-WILLIAM-1",
    [string]$OfficerName = "Denis Sherman"
)

$ErrorActionPreference = "Continue"
$base = "C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy\plugins\LSPDFR"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Устанавливаю позывной: $Callsign" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$targets = @(
    @{ Path = "$base\GrammarPolice\custom.ini"; Key = "Callsign"    },
    @{ Path = "$base\CalloutInterface.ini";     Key = "MDTCallsign" },
    @{ Path = "$base\BlueLineScanner.ini";      Key = "VizLabel"    },
    @{ Path = "$base\pdComp\config.ini";        Key = "Callsign"    }
)

$changed = 0
foreach ($t in $targets) {
    $file = Split-Path $t.Path -Leaf
    if (-not (Test-Path $t.Path)) {
        Write-Host "  пропуск $file (файла нет)" -ForegroundColor DarkGray
        continue
    }
    try {
        $content = Get-Content $t.Path -Raw -Encoding UTF8
        $pattern = "(?m)^(\s*" + $t.Key + "\s*=\s*).*$"
        $new = [regex]::Replace($content, $pattern, ('${1}' + $Callsign))
        if ($new -ne $content) {
            [System.IO.File]::WriteAllText($t.Path, $new, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "  OK  $file" -ForegroundColor Green
            $changed++
        } else {
            Write-Host "  --  $file (уже стоит нужный)" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "  ОШИБКА $file : $($_.Exception.Message)" -ForegroundColor Red
    }
}

# Имя офицера в pdComp — чтобы записи шли под твоим именем, а не "Officer"
$pd = "$base\pdComp\config.ini"
if (Test-Path $pd) {
    try {
        $c = Get-Content $pd -Raw -Encoding UTF8
        $new = [regex]::Replace($c, "(?m)^(\s*Name\s*=\s*).*$", ('${1}' + $OfficerName))
        if ($new -ne $c) {
            [System.IO.File]::WriteAllText($pd, $new, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "  OK  имя офицера в pdComp -> $OfficerName" -ForegroundColor Green
            $changed++
        }
    } catch {
        Write-Host "  ОШИБКА имени офицера: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Проверка:" -ForegroundColor Cyan
foreach ($t in $targets) {
    if (Test-Path $t.Path) {
        $line = Select-String -Path $t.Path -Pattern ("^\s*" + $t.Key + "\s*=") | Select-Object -First 1
        if ($line) { Write-Host "  $($line.Line.Trim())" }
    }
}

Write-Host ""
if ($changed) {
    Write-Host "Готово. Перезапусти игру." -ForegroundColor Green
} else {
    Write-Host "Изменений не потребовалось." -ForegroundColor Yellow
}
Write-Host "ВАЖНО: после обновления сборки Vinewood запусти этот файл снова." -ForegroundColor Yellow
Write-Host ""
Read-Host "Нажми Enter, чтобы закрыть"
