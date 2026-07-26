# Fixes officer callsign and name in all game configs (requires admin rights).
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

$targets = @(
    @{ Path = "$base\GrammarPolice\custom.ini"; Key = "Callsign";    Value = $Callsign },
    @{ Path = "$base\CalloutInterface.ini";     Key = "MDTCallsign"; Value = $Callsign },
    @{ Path = "$base\BlueLineScanner.ini";      Key = "VizLabel";    Value = $Callsign },
    @{ Path = "$base\pdComp\config.ini";        Key = "Callsign";    Value = $Callsign },
    @{ Path = "$base\pdComp\config.ini";        Key = "Name";        Value = $OfficerName }
)

$changed = 0
$failed = 0
foreach ($t in $targets) {
    $file = Split-Path $t.Path -Leaf
    if (-not (Test-Path $t.Path)) {
        Write-Host "  skip $file (нет файла)" -ForegroundColor DarkGray
        continue
    }
    try {
        $content = Get-Content $t.Path -Raw -Encoding UTF8
        $pattern = '(?m)^(\s*' + $t.Key + '\s*=\s*).*'
        $replacement = '${1}' + $t.Value
        $new = [regex]::Replace($content, $pattern, $replacement)
        if ($new -ne $content) {
            $enc = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($t.Path, $new, $enc)
            Write-Host ("  OK   " + $file + " -> " + $t.Key + " = " + $t.Value) -ForegroundColor Green
            $changed = $changed + 1
        } else {
            Write-Host ("  --   " + $file + " (" + $t.Key + " уже верный)") -ForegroundColor DarkGray
        }
    } catch {
        Write-Host ("  FAIL " + $file + " : " + $_.Exception.Message) -ForegroundColor Red
        $failed = $failed + 1
    }
}

Write-Host ""
Write-Host "Проверка:" -ForegroundColor Cyan
foreach ($t in $targets) {
    if (Test-Path $t.Path) {
        $pat = "^\s*" + $t.Key + "\s*="
        $line = Select-String -Path $t.Path -Pattern $pat | Select-Object -First 1
        if ($line) { Write-Host ("  " + (Split-Path $t.Path -Leaf) + " : " + $line.Line.Trim()) }
    }
}

Write-Host ""
if ($failed -gt 0) {
    Write-Host "Часть файлов не записалась — нужны права администратора." -ForegroundColor Red
} elseif ($changed -gt 0) {
    Write-Host "Готово! Перезапусти игру." -ForegroundColor Green
} else {
    Write-Host "Всё уже настроено." -ForegroundColor Yellow
}
Write-Host "ВАЖНО: после обновления сборки Vinewood запусти этот файл снова." -ForegroundColor Yellow
Write-Host ""
Read-Host "Нажми Enter для выхода"
