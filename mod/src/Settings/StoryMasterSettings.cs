using System;
using MCM.Abstractions.Attributes;
using MCM.Abstractions.Attributes.v2;
using MCM.Abstractions.Base.Global;
using TaleWorlds.Localization;

namespace AIInfluenceStoryMaster.Settings
{
    /// <summary>
    /// MCM settings for Story Master.  Discovered + rendered by MCM when present;
    /// when MCM is absent this type is never touched (see <see cref="SettingsBridge"/>).
    ///
    /// "Export" group: an auto-export toggle (the campaign database is written
    /// once per session launch) plus a manual "export now" button.  "Status
    /// detection" group: the heartbeat toggle.  V1 stays a read-only observer.
    ///
    /// Bool toggles (not dropdowns) on purpose: MCM re-resolves a bool's display
    /// name from its {=id} per render, so it follows in-game language switches.
    /// </summary>
    public sealed class StoryMasterSettings : AttributeGlobalSettings<StoryMasterSettings>
    {
        public override string Id => "AIInfluence_StoryMaster_v1";
        public override string DisplayName =>
            new TextObject("{=StoryMaster_Name}AI Influence: Story Master").ToString();
        public override string FolderName => "AIInfluence_StoryMaster";
        public override string FormatType => "json2";

        private const string GEditor = "{=StoryMaster_Grp_Editor}Editor";
        private const string GExport = "{=StoryMaster_Grp_Export}Database";
        private const string GEnc = "{=StoryMaster_Grp_Enc}Encyclopedia";
        private const string GStatus = "{=StoryMaster_Grp_Status}Status detection";

        // ── Editor ──────────────────────────────────────────────────────
        [SettingPropertyButton("{=StoryMaster_OpenEditor}Open editor", Order = 0,
            RequireRestart = false, Content = "{=StoryMaster_OpenEditor_C}Open",
            HintText = "{=StoryMaster_OpenEditor_H}Launch the Story Master editor (Tool folder inside this module). The editor is a desktop application: it opens as a separate window, so you have to switch windows to start working. Campaign data should be edited from the main menu.")]
        [SettingPropertyGroup(GEditor)]
        public Action OpenEditor { get; set; } = ExportActions.OpenEditor;

        // ── Campaign database (terminology + world snapshot) ────────────
        [SettingPropertyBool("{=StoryMaster_AutoExport}Auto-update database", Order = 0,
            RequireRestart = false,
            HintText = "{=StoryMaster_AutoExport_H}Update the database (heroes, clans, kingdoms, settlements, items + their metadata, and a world snapshot) once each time a campaign is loaded. Turn off to update only with the button below. [ Default: ON ]")]
        [SettingPropertyGroup(GExport)]
        public bool AutoExport { get; set; } = true;

        [SettingPropertyButton("{=StoryMaster_ExportBtn}Update database now", Order = 1,
            RequireRestart = false, Content = "{=StoryMaster_ExportNow}Update",
            HintText = "{=StoryMaster_ExportBtn_H}Update the database immediately (only works while a campaign is loaded).")]
        [SettingPropertyGroup(GExport)]
        public Action ExportNow { get; set; } = ExportActions.ExportCampaignDatabase;

        // ── Encyclopedia ────────────────────────────────────────────────
        //
        // The master switch is first and phrased positively ("Write ..."), so the
        // hint can explain what turning it OFF restores. Field toggles default to
        // the three sections 1.2.0 already wrote — an upgrading player sees no
        // change until they opt in to more.
        [SettingPropertyBool("{=StoryMaster_EncEnable}Write Story Master's encyclopedia layout", Order = 0,
            RequireRestart = false,
            HintText = "{=StoryMaster_EncEnable_H}Show the persona you author in the editor on each character's encyclopedia page. Turn OFF to leave the page entirely to AI Influence (backstory + personality only). Turning it off does not undo pages already written — use \"Restore original pages\" below for that. [ Default: ON ]")]
        [SettingPropertyGroup(GEnc)]
        public bool EncyclopediaEnabled { get; set; } = true;

        [SettingPropertyBool("{=StoryMaster_AutoEnc}Auto-sync on campaign load", Order = 1,
            RequireRestart = false,
            HintText = "{=StoryMaster_AutoEnc_H}When a campaign loads, apply each character file's persona to their encyclopedia page, so edits made in the editor show up directly in game. Only characters changed since the last sync are read. [ Default: ON ]")]
        [SettingPropertyGroup(GEnc)]
        public bool AutoSyncEncyclopedia { get; set; } = true;

        // ── Which persona fields become sections ────────────────────────
        [SettingPropertyBool("{=StoryMaster_EncDesc}Include: Description", Order = 10,
            RequireRestart = false,
            HintText = "{=StoryMaster_EncDesc_H}The free-form description you write in the editor. AI Influence never shows this on its own. [ Default: ON ]")]
        [SettingPropertyGroup(GEnc)]
        public bool EncIncludeDescription { get; set; } = true;

        [SettingPropertyBool("{=StoryMaster_EncBack}Include: Backstory", Order = 11,
            RequireRestart = false,
            HintText = "{=StoryMaster_EncBack_H}The AI-generated backstory. [ Default: ON ]")]
        [SettingPropertyGroup(GEnc)]
        public bool EncIncludeBackstory { get; set; } = true;

        [SettingPropertyBool("{=StoryMaster_EncPers}Include: Personality", Order = 12,
            RequireRestart = false,
            HintText = "{=StoryMaster_EncPers_H}The AI-generated personality. [ Default: ON ]")]
        [SettingPropertyGroup(GEnc)]
        public bool EncIncludePersonality { get; set; } = true;

        [SettingPropertyBool("{=StoryMaster_EncCog}Include: Cognitive style", Order = 13,
            RequireRestart = false,
            HintText = "{=StoryMaster_EncCog_H}How the character thinks — humour, honesty, how they hold a grudge. Adds roughly 250 characters. [ Default: OFF ]")]
        [SettingPropertyGroup(GEnc)]
        public bool EncIncludeCognitiveStyle { get; set; } = false;

        [SettingPropertyBool("{=StoryMaster_EncSpeech}Include: Speech quirks", Order = 14,
            RequireRestart = false,
            HintText = "{=StoryMaster_EncSpeech_H}How the character speaks — pace, vocabulary, manner. Adds roughly 180 characters. [ Default: OFF ]")]
        [SettingPropertyGroup(GEnc)]
        public bool EncIncludeSpeechQuirks { get; set; } = false;

        // ── Encyclopedia actions ────────────────────────────────────────
        [SettingPropertyButton("{=StoryMaster_EncBtn}Refresh encyclopedia now", Order = 20,
            RequireRestart = false, Content = "{=StoryMaster_EncNow}Sync",
            HintText = "{=StoryMaster_EncBtn_H}Refresh every character's encyclopedia entry immediately (only works while a campaign is loaded).")]
        [SettingPropertyGroup(GEnc)]
        public Action SyncEncyclopediaNow { get; set; } = ExportActions.SyncEncyclopediaNow;

        [SettingPropertyButton("{=StoryMaster_EncRestore}Restore original pages", Order = 21,
            RequireRestart = false, Content = "{=StoryMaster_EncRestore_C}Restore",
            HintText = "{=StoryMaster_EncRestore_H}Put every encyclopedia page Story Master rewrote back to what it was: the exact original where one was recorded before the first overwrite, the hand-written text from the module XML where there is one, otherwise the game's own generated text. Dead characters keep their obituary. Only works while a campaign is loaded.")]
        [SettingPropertyGroup(GEnc)]
        public Action RestoreEncyclopediaNow { get; set; } = ExportActions.RestoreEncyclopediaNow;

        // ── Status detection ────────────────────────────────────────────
        [SettingPropertyBool("{=StoryMaster_Heartbeat}Write game-state heartbeat", Order = 0,
            RequireRestart = false,
            HintText = "{=StoryMaster_Heartbeat_H}Write a small heartbeat file (~every 3s, negligible cost) so the external editor can precisely tell main-menu vs in-campaign vs paused. [ Default: ON ]")]
        [SettingPropertyGroup(GStatus)]
        public bool EnableHeartbeat { get; set; } = true;
    }
}
