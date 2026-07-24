# Build AIInfluence_StoryMaster (Release) and deploy the runtime files into the
# game's Modules folder for in-game testing.
#
# Usage:
#   .\build_and_deploy.ps1
#   .\build_and_deploy.ps1 -BannerlordPath "C:\Path\To\Mount & Blade II Bannerlord"
param(
    [string]$BannerlordPath = "E:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
)

$ErrorActionPreference = "Stop"
$src = $PSScriptRoot

Write-Host "==> dotnet build (Release)" -ForegroundColor Cyan
dotnet build "$src\AIInfluence_StoryMaster.csproj" -c Release -v minimal -p:BannerlordPath="$BannerlordPath"
if ($LASTEXITCODE -ne 0) { throw "build failed" }

$dst = Join-Path $BannerlordPath "Modules\AIInfluence_StoryMaster"
Write-Host "==> deploy to $dst" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path "$dst\bin\Win64_Shipping_Client" | Out-Null
Copy-Item "$src\SubModule.xml"        "$dst\SubModule.xml" -Force
Copy-Item "$src\module_version.txt"   "$dst\module_version.txt" -Force
Copy-Item "$src\bin\Win64_Shipping_Client\AIInfluence_StoryMaster.dll" `
          "$dst\bin\Win64_Shipping_Client\AIInfluence_StoryMaster.dll" -Force

# ModuleData (localization etc.) — copied when present (added from M2/M5).
# Remove destination first: Copy-Item -Recurse onto an existing folder nests it
# (ModuleData\ModuleData) instead of overwriting.
if (Test-Path "$src\ModuleData") {
    if (Test-Path "$dst\ModuleData") { Remove-Item "$dst\ModuleData" -Recurse -Force }
    Copy-Item "$src\ModuleData" "$dst\ModuleData" -Recurse -Force
}

# NOTE (v1.1.0 transformation): the module is the product's main body now — the
# editor no longer installs it, so the old companion_mod/ payload sync is gone.
# Release packaging (module folder with Tool/ inside) lives in ..\build_exe.ps1.

Write-Host "==> done. Enable 'AI Influence: Story Master' in the launcher (after AI Influence + Harmony)." -ForegroundColor Green
