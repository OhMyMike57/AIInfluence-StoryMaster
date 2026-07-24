using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using HarmonyLib;
using Newtonsoft.Json.Linq;
using TaleWorlds.CampaignSystem;
using TaleWorlds.Localization;

namespace AIInfluenceStoryMaster
{
    /// <summary>
    /// Writes Story Master's own encyclopedia layout into <c>Hero.EncyclopediaText</c>:
    ///
    ///   ◆ 描述          (CharacterDescription — editable freely in the editor)
    ///   ◆ 背景          (AIGeneratedBackstory)
    ///   ◆ 性格          (AIGeneratedPersonality)
    ///
    /// AI Influence's native path (<c>CharacterInfo.UpdateEncyclopediaDescription</c>)
    /// only ever writes backstory + personality — players who author a description
    /// in the editor would never see it in game, which is why we format the text
    /// ourselves instead of triggering the mod's writer.
    ///
    /// Because the mod rewrites its own two-field layout whenever it (re)loads an
    /// NPC context (interaction, persona generation, its Content Editor saves), a
    /// Harmony postfix on that method re-applies our layout right after — so the
    /// player always sees the three-section format, no matter who wrote last.
    ///
    /// Everything AI-Influence-facing is reflection + try/catch: if a future
    /// version renames the type/method we log once, the postfix simply never
    /// attaches, and the session-launch sync still covers non-interacted heroes.
    /// </summary>
    internal static class EncyclopediaSync
    {
        // Character files are "<Name> (<StringId>).json"; the id in the trailing
        // parens is the anchor (names change with title/language, ids do not).
        private static readonly Regex FileIdRe =
            new Regex(@"\(([^()]+)\)\.json$", RegexOptions.Compiled | RegexOptions.IgnoreCase);

        // Cheap pre-filter before paying for a JSON parse: any of these keys
        // holding a non-empty string means the file has something to show.
        private static readonly string[] ContentKeys =
        {
            "\"CharacterDescription\"",
            "\"AIGeneratedBackstory\"",
            "\"AIGeneratedPersonality\"",
        };

        private static bool _reflectionFailedLogged;
        private static bool _patchAttempted;

        /// <summary>UTC stamp of the last successful sync, per campaign folder, so a
        /// session-launch sync only revisits files edited since. Cleared on game restart.</summary>
        private static readonly Dictionary<string, DateTime> LastSync =
            new Dictionary<string, DateTime>(StringComparer.OrdinalIgnoreCase);

        /// <summary>Latest file-sourced fields per StringId, for the postfix: when
        /// AI Influence rewrites a hero's entry we re-apply our layout using its
        /// (freshest) backstory/personality plus the description only we know.</summary>
        private static readonly Dictionary<string, string> DescriptionCache =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        // ── Public entry points ─────────────────────────────────────────────

        /// <summary>
        /// Apply the three-section layout for every character whose JSON has any
        /// of description / backstory / personality.
        /// </summary>
        /// <param name="force">Ignore the "changed since last sync" filter.</param>
        /// <returns>Heroes updated, or -1 when the sync could not run.</returns>
        public static int Sync(bool force = false)
        {
            try
            {
                if (Campaign.Current == null) return -1;
                string folder = ExportBehavior.ResolveFolder();
                if (string.IsNullOrEmpty(folder)) return -1;

                string dir = Path.Combine(FileContract.AiSaveDataDir, folder);
                if (!Directory.Exists(dir)) return -1;

                DateTime since = DateTime.MinValue;
                if (!force) LastSync.TryGetValue(folder, out since);

                var heroesById = BuildHeroIndex();
                int synced = 0;

                foreach (string file in Directory.GetFiles(dir, "*.json", SearchOption.TopDirectoryOnly))
                {
                    try
                    {
                        Match m = FileIdRe.Match(Path.GetFileName(file));
                        if (!m.Success) continue;
                        string stringId = m.Groups[1].Value;

                        bool fresh = force || File.GetLastWriteTimeUtc(file) > since;
                        string text = File.ReadAllText(file);
                        if (!ProbeHasContent(text)) continue;

                        string desc, backstory, personality;
                        if (!TryReadFields(text, out desc, out backstory, out personality)) continue;

                        // Cache even when not fresh: the postfix needs descriptions
                        // for heroes the mod touches mid-session.
                        DescriptionCache[stringId] = desc ?? "";

                        if (!fresh) continue;
                        Hero hero;
                        if (!heroesById.TryGetValue(stringId, out hero) || hero == null) continue;
                        if (ApplyLayout(hero, desc, backstory, personality)) synced++;
                    }
                    catch (Exception exFile)
                    {
                        FileContract.Log("EncyclopediaSync: skipped " + Path.GetFileName(file)
                                         + " — " + exFile.Message);
                    }
                }

                LastSync[folder] = DateTime.UtcNow;
                FileContract.Log("EncyclopediaSync: refreshed " + synced + " hero(es)"
                                 + (force ? " (full)" : " (changed only)") + ".");
                return synced;
            }
            catch (Exception ex)
            {
                FileContract.Log("EncyclopediaSync.Sync ERROR: " + ex.Message);
                return -1;
            }
        }

        /// <summary>
        /// Attach the keep-our-layout postfix to AI Influence's encyclopedia writer.
        /// Safe to call repeatedly; runs once. No-op when AI Influence is absent or
        /// the method moved (logged once).
        /// </summary>
        public static void TryInstallPatch(Harmony harmony)
        {
            if (_patchAttempted) return;
            _patchAttempted = true;
            try
            {
                Type t = AccessTools.TypeByName("AIInfluence.CharacterInfo");
                MethodInfo target = t == null ? null : t.GetMethod(
                    "UpdateEncyclopediaDescription",
                    BindingFlags.Public | BindingFlags.Static | BindingFlags.NonPublic,
                    null, new[] { typeof(Hero), typeof(string), typeof(string) }, null);
                if (target == null)
                {
                    FileContract.Log("EncyclopediaSync: CharacterInfo.UpdateEncyclopediaDescription "
                                     + "not found — layout postfix not installed.");
                    return;
                }
                harmony.Patch(target, postfix: new HarmonyMethod(
                    typeof(EncyclopediaSync).GetMethod(nameof(AfterModWrite),
                        BindingFlags.NonPublic | BindingFlags.Static)));
                FileContract.Log("EncyclopediaSync: layout postfix installed.");
            }
            catch (Exception ex)
            {
                FileContract.Log("EncyclopediaSync.TryInstallPatch ERROR: " + ex.Message);
            }
        }

        // ── Harmony postfix ─────────────────────────────────────────────────

        /// <summary>Re-apply our layout right after AI Influence writes its own
        /// (backstory+personality only) version.  The patch args carry the freshest
        /// persona; the description comes from our file-scan cache.</summary>
        private static void AfterModWrite(Hero hero, string backstory, string personality)
        {
            try
            {
                if (hero == null) return;
                string desc;
                DescriptionCache.TryGetValue(hero.StringId ?? "", out desc);
                ApplyLayout(hero, desc, backstory, personality);
            }
            catch { /* a postfix must never break the host mod */ }
        }

        // ── Layout ──────────────────────────────────────────────────────────

        /// <summary>Compose and write the three-section text. Sections with no
        /// content are omitted; a hero with nothing at all is left untouched.</summary>
        private static bool ApplyLayout(Hero hero, string desc, string backstory, string personality)
        {
            var sb = new StringBuilder();
            AppendSection(sb, "{=StoryMaster_Enc_Desc}— Description —", desc);
            AppendSection(sb, "{=StoryMaster_Enc_Backstory}— Backstory —", backstory);
            AppendSection(sb, "{=StoryMaster_Enc_Personality}— Personality —", personality);
            if (sb.Length == 0) return false;
            hero.EncyclopediaText = new TextObject(sb.ToString(), null);
            return true;
        }

        private static void AppendSection(StringBuilder sb, string keyedTitle, string body)
        {
            if (string.IsNullOrWhiteSpace(body)) return;
            if (sb.Length > 0) sb.Append("\n\n");
            sb.Append(new TextObject(keyedTitle, null).ToString());
            sb.Append('\n');
            sb.Append(Sanitize(body.Trim()));
        }

        /// <summary>Player-authored text goes through TextObject, which parses
        /// braces as variables — swap them for fullwidth lookalikes so free-form
        /// descriptions can never break the encyclopedia page.</summary>
        private static string Sanitize(string s)
        {
            return s.Replace('{', '｛').Replace('}', '｝');
        }

        // ── File reading ────────────────────────────────────────────────────

        private static bool ProbeHasContent(string text)
        {
            foreach (string key in ContentKeys)
            {
                int i = text.IndexOf(key, StringComparison.Ordinal);
                if (i < 0) continue;
                int colon = text.IndexOf(':', i + key.Length);
                if (colon < 0) continue;
                int j = colon + 1;
                while (j < text.Length && char.IsWhiteSpace(text[j])) j++;
                // A non-empty string value, i.e. not `null` and not `""`.
                if (j < text.Length && text[j] == '"' && j + 1 < text.Length && text[j + 1] != '"')
                    return true;
            }
            return false;
        }

        private static bool TryReadFields(string jsonText,
                                          out string desc, out string backstory, out string personality)
        {
            desc = backstory = personality = null;
            try
            {
                JObject o = JObject.Parse(jsonText);
                desc = (string)o["CharacterDescription"];
                backstory = (string)o["AIGeneratedBackstory"];
                personality = (string)o["AIGeneratedPersonality"];
                return !string.IsNullOrWhiteSpace(desc)
                    || !string.IsNullOrWhiteSpace(backstory)
                    || !string.IsNullOrWhiteSpace(personality);
            }
            catch { return false; }
        }

        private static Dictionary<string, Hero> BuildHeroIndex()
        {
            var map = new Dictionary<string, Hero>(StringComparer.OrdinalIgnoreCase);
            try
            {
                foreach (Hero h in Hero.AllAliveHeroes)
                    if (h != null && !string.IsNullOrEmpty(h.StringId)) map[h.StringId] = h;
                foreach (Hero h in Hero.DeadOrDisabledHeroes)
                    if (h != null && !string.IsNullOrEmpty(h.StringId) && !map.ContainsKey(h.StringId))
                        map[h.StringId] = h;
            }
            catch (Exception ex)
            {
                FileContract.Log("EncyclopediaSync.BuildHeroIndex ERROR: " + ex.Message);
                if (!_reflectionFailedLogged) _reflectionFailedLogged = true;
            }
            return map;
        }
    }
}
