using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using TaleWorlds.CampaignSystem;
using TaleWorlds.CampaignSystem.Settlements;
using TaleWorlds.Core;
using TaleWorlds.Localization;
using TaleWorlds.ObjectSystem;

namespace AIInfluenceStoryMaster
{
    /// <summary>
    /// Scans MBObjectManager for every "name + StringId" object and writes a
    /// per-campaign terminology library the external tool reads to turn IDs into
    /// readable names (and, in M3, names back into IDs). Replaces the tool's
    /// previous dependency on the external ProemConfig export.
    /// </summary>
    internal static class TerminologyExport
    {
        private static readonly JsonSerializerSettings JsonSettings = new JsonSerializerSettings
        {
            Formatting = Formatting.Indented,
            NullValueHandling = NullValueHandling.Ignore,
        };

        public static void Export(string campaignFolder)
        {
            try
            {
                // Each category is isolated so one failing type can't abort the
                // whole export, and the log names which one if anything throws.
                var root = new Dictionary<string, object>
                {
                    ["schema_version"] = FileContract.SchemaVersion,
                    ["exported_at"] = DateTime.UtcNow.ToString("o"),
                    ["mod_version"] = SubModule.ModVersion,
                    ["heroes"] = SafeBuild("heroes", BuildHeroes),
                    ["troops"] = SafeBuild("troops", BuildTroops),
                    ["clans"] = SafeBuild("clans", BuildClans),
                    ["kingdoms"] = SafeBuild("kingdoms", BuildKingdoms),
                    ["cultures"] = SafeBuild("cultures", BuildCultures),
                    ["settlements"] = SafeBuild("settlements", BuildSettlements),
                    ["items"] = SafeBuild("items", BuildItems),
                };
                string json = JsonConvert.SerializeObject(root, JsonSettings);
                string path = Path.Combine(FileContract.CampaignStorytoolsDir(campaignFolder), "terminology.json");
                FileContract.AtomicWrite(path, json);
                FileContract.Log("Terminology exported: " + path);
            }
            catch (Exception ex)
            {
                FileContract.Log("TerminologyExport ERROR: " + ex);  // full stack
            }
        }

        private static Dictionary<string, object> SafeBuild(
            string label, Func<Dictionary<string, object>> build)
        {
            try { return build(); }
            catch (Exception ex)
            {
                FileContract.Log("  terminology build '" + label + "' failed: " + ex);
                return new Dictionary<string, object>();
            }
        }

        private static System.Collections.Generic.IEnumerable<T> SafeList<T>() where T : MBObjectBase
        {
            var mgr = MBObjectManager.Instance;
            var list = mgr != null ? mgr.GetObjectTypeList<T>() : null;
            return (System.Collections.Generic.IEnumerable<T>)list
                   ?? System.Array.Empty<T>();
        }

        // Heroes / Clans / Kingdoms are campaign-runtime objects: they live in
        // CampaignObjectManager, NOT the generic MBObjectManager type lists, so
        // GetObjectTypeList<T>() returns nothing for them.  Enumerate them from
        // Campaign.Current instead (verified against TaleWorlds.CampaignSystem.Campaign).
        private static System.Collections.Generic.IEnumerable<Hero> AllHeroes()
        {
            var c = Campaign.Current;
            if (c == null) yield break;
            if (c.AliveHeroes != null)
                foreach (var h in c.AliveHeroes) yield return h;
            if (c.DeadOrDisabledHeroes != null)
                foreach (var h in c.DeadOrDisabledHeroes) yield return h;
        }

        private static System.Collections.Generic.IEnumerable<T> Campaigned<T>(
            System.Collections.Generic.IEnumerable<T> list)
            => list ?? System.Linq.Enumerable.Empty<T>();

        private static string Str(TextObject t)
        {
            try { return t != null ? t.ToString() : null; }
            catch { return null; }
        }

        private static Dictionary<string, object> BuildHeroes()
        {
            var d = new Dictionary<string, object>();
            foreach (Hero h in AllHeroes())
            {
                try
                {
                    if (h == null || string.IsNullOrEmpty(h.StringId)) continue;
                    string kingdom = (h.Clan != null && h.Clan.Kingdom != null)
                        ? h.Clan.Kingdom.StringId : null;
                    // MapFaction is the hero's effective faction (covers minor /
                    // clanless heroes whose Clan.Kingdom is null) — the robust key
                    // for the tool's two-level faction → clan filter.
                    string mapFaction = null;
                    try { mapFaction = h.MapFaction != null ? h.MapFaction.StringId : null; } catch { }
                    d[h.StringId] = new Dictionary<string, object>
                    {
                        ["name"] = Str(h.Name),
                        ["clan"] = h.Clan != null ? h.Clan.StringId : null,
                        ["kingdom"] = kingdom,
                        ["map_faction"] = mapFaction,
                        ["culture"] = h.Culture != null ? h.Culture.StringId : null,
                        ["gender"] = h.IsFemale ? "female" : "male",
                        ["age"] = (int)h.Age,
                        ["alive"] = h.IsAlive,
                        ["occupation"] = h.CharacterObject != null ? h.CharacterObject.Occupation.ToString() : null,
                        ["is_lord"] = h.IsLord,
                        ["is_wanderer"] = h.IsWanderer,
                        ["is_notable"] = h.IsNotable,
                        ["is_clan_leader"] = (h.Clan != null && h.Clan.Leader == h),
                        ["is_minor_faction_hero"] = h.IsMinorFactionHero,
                        ["is_prisoner"] = h.IsPrisoner,
                        ["is_child"] = h.IsChild,
                        ["is_player"] = (h == Hero.MainHero),
                        // Template heroes are blueprint NPCs (e.g. wanderer
                        // archetypes like "盾女") — the tool excludes them from
                        // the real-NPC character database by default.
                        ["is_template"] = (h.CharacterObject != null && h.IsTemplate),
                        // Immediate family (ids) — enables future relationship filters.
                        ["father"] = h.Father != null ? h.Father.StringId : null,
                        ["mother"] = h.Mother != null ? h.Mother.StringId : null,
                        ["spouse"] = h.Spouse != null ? h.Spouse.StringId : null,
                    };
                }
                catch { /* skip bad hero */ }
            }
            return d;
        }

        private static Dictionary<string, object> BuildTroops()
        {
            var d = new Dictionary<string, object>();
            foreach (CharacterObject c in SafeList<CharacterObject>())
            {
                try
                {
                    if (c == null || c.IsHero || string.IsNullOrEmpty(c.StringId)) continue;
                    d[c.StringId] = new Dictionary<string, object>
                    {
                        ["name"] = Str(c.Name),
                        ["culture"] = c.Culture != null ? c.Culture.StringId : null,
                        ["tier"] = c.Tier,
                    };
                }
                catch { /* skip */ }
            }
            return d;
        }

        private static Dictionary<string, object> BuildClans()
        {
            var d = new Dictionary<string, object>();
            foreach (Clan c in Campaigned(Campaign.Current?.Clans))
            {
                try
                {
                    if (c == null || string.IsNullOrEmpty(c.StringId)) continue;
                    d[c.StringId] = new Dictionary<string, object>
                    {
                        ["name"] = Str(c.Name),
                        ["kingdom"] = c.Kingdom != null ? c.Kingdom.StringId : null,
                        ["culture"] = c.Culture != null ? c.Culture.StringId : null,
                        ["tier"] = c.Tier,
                        ["minor"] = c.IsMinorFaction,
                        ["under_mercenary_service"] = c.IsUnderMercenaryService,
                        ["is_rebel"] = c.IsRebelClan,
                        ["is_bandit"] = c.IsBanditFaction,
                        ["leader"] = c.Leader != null ? c.Leader.StringId : null,
                        ["eliminated"] = c.IsEliminated,
                    };
                }
                catch { /* skip */ }
            }
            return d;
        }

        private static Dictionary<string, object> BuildKingdoms()
        {
            var d = new Dictionary<string, object>();
            foreach (Kingdom k in Campaigned(Campaign.Current?.Kingdoms))
            {
                try
                {
                    if (k == null || string.IsNullOrEmpty(k.StringId)) continue;
                    d[k.StringId] = new Dictionary<string, object>
                    {
                        ["name"] = Str(k.Name),
                        ["culture"] = k.Culture != null ? k.Culture.StringId : null,
                        ["ruler_clan"] = k.RulingClan != null ? k.RulingClan.StringId : null,
                        ["leader"] = k.Leader != null ? k.Leader.StringId : null,
                        ["eliminated"] = k.IsEliminated,
                    };
                }
                catch { /* skip */ }
            }
            return d;
        }

        private static Dictionary<string, object> BuildCultures()
        {
            var d = new Dictionary<string, object>();
            foreach (CultureObject c in SafeList<CultureObject>())
            {
                try
                {
                    if (c == null || string.IsNullOrEmpty(c.StringId)) continue;
                    d[c.StringId] = new Dictionary<string, object> { ["name"] = Str(c.Name) };
                }
                catch { /* skip */ }
            }
            return d;
        }

        private static Dictionary<string, object> BuildSettlements()
        {
            var d = new Dictionary<string, object>();
            foreach (Settlement s in SafeList<Settlement>())
            {
                try
                {
                    if (s == null || string.IsNullOrEmpty(s.StringId)) continue;
                    string type = s.IsTown ? "town" : s.IsCastle ? "castle" : s.IsVillage ? "village" : "other";
                    string bound = (s.IsVillage && s.Village != null && s.Village.Bound != null)
                        ? s.Village.Bound.StringId : null;
                    d[s.StringId] = new Dictionary<string, object>
                    {
                        ["name"] = Str(s.Name),
                        ["type"] = type,
                        ["culture"] = s.Culture != null ? s.Culture.StringId : null,
                        ["owner_clan"] = s.OwnerClan != null ? s.OwnerClan.StringId : null,
                        ["bound"] = bound,
                    };
                }
                catch { /* skip */ }
            }
            return d;
        }

        private static Dictionary<string, object> BuildItems()
        {
            var d = new Dictionary<string, object>();
            foreach (ItemObject it in SafeList<ItemObject>())
            {
                try
                {
                    if (it == null || string.IsNullOrEmpty(it.StringId)) continue;
                    d[it.StringId] = new Dictionary<string, object>
                    {
                        ["name"] = Str(it.Name),
                        ["culture"] = it.Culture != null ? it.Culture.StringId : null,
                    };
                }
                catch { /* skip */ }
            }
            return d;
        }
    }
}
