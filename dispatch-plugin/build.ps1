# Сборка плагина DispatchOne.MDT (RagePluginHook/LSPDFR).
# Требует .NET Framework csc (есть в Windows) и установленные GTA V + RPH + LSPDFR + CalloutInterface.
$ErrorActionPreference = "Stop"
$csc  = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$root = "C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy"
$dir  = Split-Path -Parent $MyInvocation.MyCommand.Path

New-Item -ItemType Directory -Force -Path "$dir\refs","$dir\out" | Out-Null

# 1) stub-референс RagePluginHook (в игре подменяется настоящей сборкой)
& $csc /target:library /nologo /out:"$dir\refs\RagePluginHook.dll" "$dir\stub\RageStub.cs"

# 2) сам плагин
$refs = @(
  "$dir\refs\RagePluginHook.dll",
  "$root\plugins\LSPD First Response.dll",
  "$root\CalloutInterfaceAPI.dll"
)
$refArgs = ($refs | ForEach-Object { "/reference:`"$_`"" }) -join " "
$out = "$dir\out\DispatchOne.MDT.dll"
Invoke-Expression "& `"$csc`" /target:library /nologo /nowarn:1684 /out:`"$out`" $refArgs `"$dir\DispatchOneMdt.cs`""

if (Test-Path $out) { Write-Host ("OK -> " + $out + "  (" + (Get-Item $out).Length + " bytes)") }
else { throw "build failed" }
