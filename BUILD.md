# Build Instructions

This document describes how to reproduce the released archive
`AIInfluence_StoryMaster_v1.2.0.zip` from this source tree.

The release consists of **two halves**, built in order:

1. **The module** — a C# Bannerlord module (`mod/`) targeting .NET Framework 4.7.2,
   producing `AIInfluence_StoryMaster.dll`.
2. **The editor** — a Python 3 / Tkinter desktop application (repository root),
   frozen with PyInstaller into a self-contained folder that ships inside the
   module's `Tool/` subfolder.

---

## 1. Prerequisites

| Requirement | Version used for the official build | Notes |
|---|---|---|
| Windows | 10 (19045) | The editor is Windows-first; the build scripts are PowerShell |
| Python | 3.12 | Must be on `PATH` as `python` |
| PyInstaller | 6.21.0 | `pip install pyinstaller==6.21.0` |
| .NET SDK | 8.0 or newer | Builds a `net472` target; any recent SDK works |
| Mount & Blade II: Bannerlord | 1.2.12+ | **Required** — the C# project references the game's own assemblies |
| Bannerlord.Harmony | any | Required — referenced for `0Harmony.dll` |

Python packages (`requirements.txt`):

```
ttkbootstrap>=1.10.0
psutil>=5.9.0
Pillow>=10.0.0
```

Install them with:

```bash
pip install -r requirements.txt pyinstaller==6.21.0
```

### Why a game installation is needed

The module compiles against TaleWorlds' assemblies, which ship with the game and
are not redistributable. `mod/AIInfluence_StoryMaster.csproj` references them via
`HintPath` from your Bannerlord installation:

```
TaleWorlds.Library, TaleWorlds.Core, TaleWorlds.ObjectSystem, TaleWorlds.Engine,
TaleWorlds.Localization, TaleWorlds.MountAndBlade, TaleWorlds.CampaignSystem,
Newtonsoft.Json      →  <Bannerlord>\bin\Win64_Shipping_Client\
0Harmony             →  <Bannerlord>\Modules\Bannerlord.Harmony\bin\Win64_Shipping_Client\
```

All of these are reference-only (`<Private>false</Private>`); none are copied
into the output. The single NuGet dependency, `Bannerlord.MCM` 5.11.4, is
referenced with `ExcludeAssets=runtime` — reference assemblies only, so no MCM
code is bundled either.

**The output DLL therefore contains only this project's own compiled code.**

---

## 2. Build the module (C#)

The default game path in the scripts is `E:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord`.
Override it with `-BannerlordPath` (or `-p:BannerlordPath=`) to match your install.

```powershell
cd mod
.\build_and_deploy.ps1 -BannerlordPath "C:\Path\To\Mount & Blade II Bannerlord"
```

Or with `dotnet` directly, if you only want the DLL and not the deploy step:

```powershell
dotnet build mod\AIInfluence_StoryMaster.csproj -c Release `
    -p:BannerlordPath="C:\Path\To\Mount & Blade II Bannerlord"
```

**Output:** `mod\bin\Win64_Shipping_Client\AIInfluence_StoryMaster.dll`

The build is configured `Deterministic=true` with `DebugType=none`, so repeated
builds of the same source produce a byte-identical DLL.

> `build_and_deploy.ps1` also copies the module into your game's `Modules\`
> folder for in-place testing. That step is a convenience only and is not part of
> producing the release archive.

---

## 3. Build the editor and package the release

From the repository root:

```powershell
.\build_exe.ps1
```

The version is read from `VERSION.txt` (currently `1.2.0`); pass `-Version 1.2.0`
to set it explicitly, or `-Clean` to wipe `build/` and `dist/` first.

This script:

1. Verifies `mod\bin\Win64_Shipping_Client\AIInfluence_StoryMaster.dll` exists and
   that `mod\module_version.txt` matches the version being packaged.
2. Runs PyInstaller against `StoryMaster.spec` (onedir, no UPX, windowed) →
   `dist\StoryMaster\`.
3. Assembles the module folder `dist\AIInfluence_StoryMaster\`:
   `SubModule.xml`, `module_version.txt`, `bin\Win64_Shipping_Client\*.dll`,
   `ModuleData\` (localization XML).
4. Moves the frozen editor in as `Tool\`, and writes the three localized
   `README_*.txt` files from the templates in `packaging\`.
5. Zips the module folder into `dist\AIInfluence_StoryMaster_v1.2.0.zip`.

**Final artifact:** `dist\AIInfluence_StoryMaster_v1.2.0.zip` (~23.5 MB)

### Resulting archive layout

```
AIInfluence_StoryMaster/
├─ SubModule.xml
├─ module_version.txt
├─ bin/Win64_Shipping_Client/AIInfluence_StoryMaster.dll
├─ ModuleData/Languages/{CNt,CNs}/…
└─ Tool/                         ← the frozen editor
   ├─ StoryMaster.exe
   ├─ _internal/                 ← Python runtime, ttkbootstrap, Pillow, assets
   └─ README_EN.txt / README_CNt.txt / README_CNs.txt
```

`StoryMaster.spec` bundles only three of this project's own asset groups —
`locales/` (terminology JSON), `assets/` (icon and splash image) and
`VERSION.txt` — plus the ttkbootstrap theme data and Pillow hidden imports that
PyInstaller needs. Internal development documents are deliberately **not**
bundled.

---

## 4. Verifying the build

The editor has a headless self-test that constructs the full UI and exits:

```bash
python StoryMaster.py --selftest          # from source
dist\AIInfluence_StoryMaster\Tool\StoryMaster.exe --selftest   # frozen
```

Exit code `0` means the application initialised correctly.

The repository also carries the regression scripts used before each release:

```bash
python scripts/startup_sanity_check.py
python scripts/world_regression_check.py
python scripts/main_workspace_regression_check.py
```

`scripts/` contains around 45 such checks; they are development-only and are
excluded from the frozen build (see `excludes` in `StoryMaster.spec`).

---

## 5. Security notes for reviewers

This section documents, with file references, everything the application does
that a security review would reasonably want to check.

### No network access whatsoever

**The application contains no networking code of any kind.** There are no
imports of `requests`, `urllib`, `http.client`, `socket`, `websocket`, `aiohttp`
or `httpx` anywhere in the Python source, and no `HttpClient`, `WebClient` or
`WebRequest` in the C# source. It does not phone home, check for updates,
send telemetry, or download anything. It never has.

There are no bundled credentials, API keys or tokens.

### What it reads and writes

The editor's entire purpose is to edit the save data of another mod,
**AI Influence**, which stores campaign state as JSON files on disk.

- **Reads/writes** JSON files under
  `<Bannerlord>\Modules\AIInfluence\save_data\` — this is the mod's own data
  folder and the whole point of the tool.
- **Writes** its own settings, logs, terminology cache and backups to
  `%APPDATA%\AIInfluenceStoryTools\` (see `services/app_paths.py`).
- **Never touches** the game's actual save files (`.sav`) or any file outside
  those two locations.
- Every write goes through `safe_write_json_with_backup()`
  (`services/backup_service.py`), which takes a backup before modifying a file.

### Reading the Windows registry

`services/path_service.py` (~line 140) reads three **Steam** registry values to
auto-detect the Bannerlord installation folder, so the user does not have to
type the path manually:

```
HKCU\Software\Valve\Steam                      → SteamPath
HKLM\SOFTWARE\WOW6432Node\Valve\Steam          → InstallPath
HKLM\SOFTWARE\Valve\Steam                      → InstallPath
```

These are **read-only** queries. The application never writes to the registry.

### Launching other processes

There are exactly two places where a process is started, both user-initiated:

1. **`mod/src/Settings/ExportActions.cs` (~line 84)** — the in-game MCM
   "Open Editor" button launches `Tool\StoryMaster.exe`, a fixed path inside the
   module's own folder, and only after checking that the file exists.
2. **`ui/backup_tab.py` (~line 288)** — the "Open" button in the Backup Center
   opens the selected backup folder in the OS file manager
   (`os.startfile` on Windows, `xdg-open` otherwise).

Neither accepts an arbitrary path from a remote source, and there is no
`eval`, `exec`, dynamic code loading, or code download anywhere in the shipped
application.

### Why the download is flagged as containing an executable

The archive contains `Tool\StoryMaster.exe`, a PyInstaller onedir build. This is
the editor itself: a standard Python + Tkinter desktop application, frozen so
that players do not need to install Python. UPX compression is deliberately
disabled in `StoryMaster.spec` (`upx=False`) to reduce antivirus false
positives. The exe can be reproduced exactly from this repository by following
sections 1–3 above.
