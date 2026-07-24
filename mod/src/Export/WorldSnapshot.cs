using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using TaleWorlds.CampaignSystem;
using TaleWorlds.CampaignSystem.Settlements;
using TaleWorlds.ObjectSystem;

namespace AIInfluenceStoryMaster
{
    /// <summary>
    /// Read-only snapshot of the live world (wars, kingdom rulers, settlement
    /// owners, player status) so the tool can offer context-aware editing
    /// (e.g. only list real / relevant kingdoms). Cheap; refreshed daily.
    /// </summary>
    internal static class WorldSnapshot
    {
        public static void Export(string campaignFolder)
        {
            try
            {
                if (Campaign.Current == null) return;
                var mgr = MBObjectManager.Instance;
                if (mgr == null) return;

                var kingdomObjs = mgr.GetObjectTypeList<Kingdom>();
                var kingdoms = new List<object>();
                if (kingdomObjs != null)
                {
                    foreach (Kingdom k in kingdomObjs)
                    {
                        try
                        {
                            if (k == null || k.IsEliminated || string.IsNullOrEmpty(k.StringId)) continue;
                            var wars = new List<string>();
                            foreach (Kingdom other in kingdomObjs)
                            {
                                if (other == null || other == k || other.IsEliminated) continue;
                                try { if (k.IsAtWarWith(other)) wars.Add(other.StringId); }
                                catch { /* skip pair */ }
                            }
                            kingdoms.Add(new Dictionary<string, object>
                            {
                                ["id"] = k.StringId,
                                ["name"] = k.Name != null ? k.Name.ToString() : null,
                                ["ruler_clan"] = k.RulingClan != null ? k.RulingClan.StringId : null,
                                ["at_war_with"] = wars,
                            });
                        }
                        catch { /* skip kingdom */ }
                    }
                }

                var owners = new Dictionary<string, string>();
                var settlementObjs = mgr.GetObjectTypeList<Settlement>();
                if (settlementObjs != null)
                {
                    foreach (Settlement s in settlementObjs)
                    {
                        if (s == null || string.IsNullOrEmpty(s.StringId)) continue;
                        try { if (s.OwnerClan != null) owners[s.StringId] = s.OwnerClan.StringId; }
                        catch { /* skip */ }
                    }
                }

                Clan player = Clan.PlayerClan;
                var root = new Dictionary<string, object>
                {
                    ["schema_version"] = FileContract.SchemaVersion,
                    ["exported_at"] = DateTime.UtcNow.ToString("o"),
                    ["campaign_day"] = SafeNowDays(),
                    ["player_clan"] = player != null ? player.StringId : null,
                    ["player_kingdom"] = (player != null && player.Kingdom != null) ? player.Kingdom.StringId : null,
                    ["kingdoms"] = kingdoms,
                    ["settlement_owners"] = owners,
                };

                string json = JsonConvert.SerializeObject(root, Formatting.Indented);
                string path = Path.Combine(FileContract.CampaignStorytoolsDir(campaignFolder), "world_snapshot.json");
                FileContract.AtomicWrite(path, json);
            }
            catch (Exception ex)
            {
                FileContract.Log("WorldSnapshot ERROR: " + ex);  // full stack
            }
        }

        private static double SafeNowDays()
        {
            try { return CampaignTime.Now.ToDays; } catch { return 0.0; }
        }
    }
}
