# Build the release package for "AI Influence: Story Master".
#
# Since v1.1.0 the MODULE is the product's main body: the release artifact is a
# ready-to-install Bannerlord module folder with the editor inside its Tool/
# subfolder.  Players unzip it into "Mount & Blade II Bannerlord\Modules" and
# tick it in the launcher — the standard module workflow.
#
#   dist\AIInfluence_StoryMaster\
#     SubModule.xml / module_version.txt
#     bin\Win64_Shipping_Client\AIInfluence_StoryMaster.dll
#     ModuleData\...
#     Tool\                      <- the frozen editor (PyInstaller onedir)
#       StoryMaster.exe, _internal\, README_*.txt
#   dist\AIInfluence_StoryMaster_v<ver>.zip   (zip root = the module folder)
#
# Usage:
#   .\build_exe.ps1                 # version read from VERSION.txt
#   .\build_exe.ps1 -Version 1.1.0
#   .\build_exe.ps1 -Clean          # wipe build/ and dist/ first
#   .\build_exe.ps1 -DeployGame     # additionally copy the module (incl. Tool)
#                                   # into the game's Modules for in-place testing
#
# The module DLL must already be built (mod\build_and_deploy.ps1); this script
# packages, it does not compile C#.
#
# NOTE: this script is intentionally ASCII-only. Windows PowerShell 5.1 reads
# a UTF-8 (no-BOM) .ps1 as the system ANSI codepage, which mojibakes any CJK
# literal and breaks parsing. User-facing Chinese text lives in
# packaging\dist_readme_*.txt (UTF-8) and is read at runtime.
param(
    [string]$Version = "",
    [switch]$Clean,
    [switch]$DeployGame,
    [string]$BannerlordPath = "E:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not $Version) {
    if (Test-Path "$root\VERSION.txt") { $Version = (Get-Content "$root\VERSION.txt" -Raw).Trim() }
    else { $Version = "dev" }
}

if ($Clean) {
    Remove-Item "$root\build", "$root\dist" -Recurse -Force -ErrorAction SilentlyContinue
}

# ── Preflight: the module half must be built already ─────────────────────
$modDll = "$root\mod\bin\Win64_Shipping_Client\AIInfluence_StoryMaster.dll"
if (-not (Test-Path $modDll)) {
    throw "module DLL not found ($modDll) - run mod\build_and_deploy.ps1 first"
}
$modVer = (Get-Content "$root\mod\module_version.txt" -Raw).Trim()
if ($modVer -ne $Version) {
    throw "version mismatch: module is $modVer, packaging as $Version - keep the bundle same-versioned"
}

Write-Host "==> PyInstaller (onedir) v$Version" -ForegroundColor Cyan
# PyInstaller logs progress to stderr; under EAP=Stop that would be treated as a
# terminating error. Drop to Continue for the native call and gate on exit code.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
# Pin dist/work paths to the repo root so the build is independent of the current
# working directory (the .spec uses paths relative to CWD; without this, running
# from a subfolder scatters build/ and dist/ there).
& python -m PyInstaller --noconfirm --distpath "$root\dist" --workpath "$root\build" "$root\StoryMaster.spec"
$code = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($code -ne 0) { throw "pyinstaller failed (exit $code)" }

$toolBuild = "$root\dist\StoryMaster"
if (-not (Test-Path "$toolBuild\StoryMaster.exe")) { throw "exe not produced" }

# ── Assemble the module folder ───────────────────────────────────────────
$modOut = "$root\dist\AIInfluence_StoryMaster"
Write-Host "==> assembling module folder -> $modOut" -ForegroundColor Cyan
if (Test-Path $modOut) { Remove-Item $modOut -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$modOut\bin\Win64_Shipping_Client" | Out-Null
Copy-Item "$root\mod\SubModule.xml"      "$modOut\SubModule.xml" -Force
Copy-Item "$root\mod\module_version.txt" "$modOut\module_version.txt" -Force
Copy-Item $modDll                        "$modOut\bin\Win64_Shipping_Client\AIInfluence_StoryMaster.dll" -Force
if (Test-Path "$root\mod\ModuleData") {
    Copy-Item "$root\mod\ModuleData" "$modOut\ModuleData" -Recurse -Force
}

# The editor moves inside the module as Tool\.
Move-Item $toolBuild "$modOut\Tool"

# Run-me notes: read each UTF-8 template, substitute the version, write into Tool\.
$readmes = @{
    "packaging\dist_readme_en.txt"  = "README_EN.txt"
    "packaging\dist_readme_cnt.txt" = "README_CNt.txt"
    "packaging\dist_readme_cns.txt" = "README_CNs.txt"
}
foreach ($src in $readmes.Keys) {
    $tmplPath = "$root\$src"
    if (Test-Path $tmplPath) {
        $tmpl = (Get-Content $tmplPath -Raw -Encoding UTF8) -replace '\{VERSION\}', $Version
        Set-Content -Path "$modOut\Tool\$($readmes[$src])" -Value $tmpl -Encoding UTF8
    }
}

# ── Zip (root = the module folder, ready for Modules\) ──────────────────
$zipBase = "$root\dist\AIInfluence_StoryMaster_v$Version"
$zip = "$zipBase.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host "==> zipping -> $zip" -ForegroundColor Cyan
# Python's shutil.make_archive: single AIInfluence_StoryMaster/ root AND
# spec-compliant forward-slash separators (PS 5.1 Compress-Archive and .NET
# Framework ZipFile both emit backslash entry names).
& python -c "import shutil,sys; shutil.make_archive(sys.argv[1],'zip',sys.argv[2],'AIInfluence_StoryMaster')" $zipBase "$root\dist"
if ($LASTEXITCODE -ne 0) { throw "zip step failed (exit $LASTEXITCODE)" }

# ── Optional: mirror into the game's Modules for in-place testing ────────
if ($DeployGame) {
    $gameMod = Join-Path $BannerlordPath "Modules\AIInfluence_StoryMaster"
    Write-Host "==> deploying full module (incl. Tool) -> $gameMod" -ForegroundColor Cyan
    # Preserve the module's own logs/ across redeploys.
    New-Item -ItemType Directory -Force -Path $gameMod | Out-Null
    foreach ($item in Get-ChildItem $modOut) {
        $dst = Join-Path $gameMod $item.Name
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        Copy-Item $item.FullName $dst -Recurse -Force
    }
}

Write-Host "==> done: $zip" -ForegroundColor Green
