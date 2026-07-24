# AI Influence: Story Master

A companion module and campaign editor for the *Mount & Blade II: Bannerlord*
mod **[AI Influence](https://www.nexusmods.com/mountandblade2bannerlord/mods/9711)**.

AI Influence gives NPCs LLM-driven dialogue and stores each campaign's state —
characters, conversation histories, memories, world info, dynamic events,
diseases — as JSON files on disk. Story Master lets players read and edit all of
that through a proper interface instead of hand-editing JSON.

**Current release:** v1.2.0 · Requires AI Influence 5.0.7 or 6.0+

---

## What's in this repository

The product ships as a single Bannerlord module with the editor inside it.
Both halves are built from this tree:

| Path | What it is |
|---|---|
| `mod/` | The **C# Bannerlord module** (`net472`). Exports the campaign database so IDs resolve to real in-game names, reports game state, syncs persona edits to the encyclopedia, and provides the MCM settings page. |
| `StoryMaster.py` | Editor entry point — the main orchestrator. |
| `ui/` | Tab and dialog assembly. |
| `controllers/` | Interaction flow and selection logic. |
| `services/` | Data and I/O layer — **framework-agnostic core** (settings, backup, staging, world/character, diseases, dynamic events, terminology, paths, RAG interop). |
| `dialogs/` | Standalone sub-windows. |
| `widgets/` | Reusable UI components. |
| `i18n/` | Dictionary-based localization (`zh_TW` / `zh_CN` / `en`). |
| `locales/terminology/` | Terminology JSON used to resolve game IDs to names. |
| `scripts/` | ~45 regression, smoke and audit scripts (development only — not shipped). |
| `assets/`, `packaging/` | Icon, splash image, and the localized README templates written into the release. |

## Building

See **[BUILD.md](BUILD.md)** for full instructions, prerequisites and the
reproduction steps for the released archive.

Short version — on Windows, with Python 3.12, the .NET SDK and Bannerlord installed:

```powershell
pip install -r requirements.txt pyinstaller==6.21.0
cd mod; .\build_and_deploy.ps1 -BannerlordPath "<your Bannerlord folder>"; cd ..
.\build_exe.ps1
```

Produces `dist\AIInfluence_StoryMaster_v1.2.0.zip`.

## Architecture notes

- **Logic and UI are strictly separated.** `services/` is pure, framework-free
  Python, so the regression scripts can import it without Tkinter.
- **Staged editing.** Edits accumulate in a staging buffer and are committed by
  an explicit Save, so a mistake can always be cancelled.
- **Minimal writes with automatic backups.** Every file write goes through
  `safe_write_json_with_backup()`, which backs the file up first.
- **Three-tier name resolution.** Campaign terminology cache → language file →
  fallback → raw ID.
- **No network access.** The application never connects to the internet. See the
  security notes in [BUILD.md](BUILD.md#5-security-notes-for-reviewers).

## Tech stack

Python 3.12 · Tkinter · ttkbootstrap · Pillow · psutil · PyInstaller (onedir)
C# / .NET Framework 4.7.2 · Harmony · MCM (optional soft dependency)

## Credits

- Story Master — Cartoonist57
- AI Influence (the parent mod) — MFiveM5
