using System;
using System.IO;
using Newtonsoft.Json;
using TaleWorlds.CampaignSystem;

namespace AIInfluenceStoryMaster
{
    /// <summary>
    /// Writes <c>heartbeat.json</c> to the global storytools dir so the external
    /// tool can detect the precise game state (main menu / in campaign / paused)
    /// and freshness. Driven from real-time <see cref="SubModule.OnApplicationTick"/>
    /// so it keeps updating even when the campaign clock is paused — daily ticks
    /// alone would go stale on a paused game and look like "main menu".
    /// </summary>
    internal static class Heartbeat
    {
        // Remembered while a campaign is loaded so the tool can, at the main menu,
        // still tell whether it has the *last-played* campaign open (vs some other
        // one). Only updated in-campaign, so tool-side writes at the main menu
        // can't move it. Resets on game restart (falls back to newest-by-mtime).
        private static string _lastCampaignId;

        public static void Write()
        {
            try
            {
                if (!FileContract.AiInfluenceInstalled) return;

                Campaign c = Campaign.Current;
                bool inCampaign = c != null;
                bool paused = inCampaign && IsPaused(c);

                string activeId = inCampaign ? FileContract.NewestCampaignFolder() : null;
                if (inCampaign && !string.IsNullOrEmpty(activeId))
                    _lastCampaignId = activeId;
                // At the main menu, surface the last-played campaign so the tool
                // can distinguish "editing the last-loaded save" from "editing
                // some other save". Fresh launch (no campaign yet) → newest folder.
                string lastId = _lastCampaignId ?? FileContract.NewestCampaignFolder();

                var data = new HeartbeatData
                {
                    schema_version = FileContract.SchemaVersion,
                    mod = "AIInfluence_StoryMaster",
                    mod_version = SubModule.ModVersion,
                    state = !inCampaign ? "main_menu" : (paused ? "paused" : "in_campaign"),
                    is_paused = paused,
                    unique_game_id = inCampaign ? SafeUniqueId(c) : null,
                    active_campaign_id = activeId,
                    last_campaign_id = lastId,
                    campaign_day = inCampaign ? (double?)SafeNowDays() : null,
                    player_clan_id = inCampaign ? SafePlayerClanId() : null,
                    wrote_at = DateTime.UtcNow.ToString("o"),
                };

                string json = JsonConvert.SerializeObject(data, Formatting.Indented);
                string path = Path.Combine(FileContract.GlobalStorytoolsDir(), "heartbeat.json");
                FileContract.AtomicWrite(path, json);
            }
            catch (Exception ex)
            {
                FileContract.Log("Heartbeat.Write ERROR: " + ex.Message);
            }
        }

        private static bool IsPaused(Campaign c)
        {
            try { return c.TimeControlMode == CampaignTimeControlMode.Stop; }
            catch { return false; }
        }

        private static string SafeUniqueId(Campaign c)
        {
            try { return c.UniqueGameId; } catch { return null; }
        }

        private static double SafeNowDays()
        {
            try { return CampaignTime.Now.ToDays; } catch { return 0.0; }
        }

        private static string SafePlayerClanId()
        {
            try { return Clan.PlayerClan != null ? Clan.PlayerClan.StringId : null; }
            catch { return null; }
        }
    }

    /// <summary>DTO; lowercase property names map 1:1 to the JSON contract keys.</summary>
    internal class HeartbeatData
    {
        public int schema_version { get; set; }
        public string mod { get; set; }
        public string mod_version { get; set; }
        public string state { get; set; }
        public bool is_paused { get; set; }
        public string unique_game_id { get; set; }
        public string active_campaign_id { get; set; }
        public string last_campaign_id { get; set; }
        public double? campaign_day { get; set; }
        public string player_clan_id { get; set; }
        public string wrote_at { get; set; }
    }
}
