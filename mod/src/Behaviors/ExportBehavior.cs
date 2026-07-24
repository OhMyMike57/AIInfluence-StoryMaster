using System;
using TaleWorlds.CampaignSystem;
using AIInfluenceStoryMaster.Settings;

namespace AIInfluenceStoryMaster
{
    /// <summary>
    /// Exports the per-campaign "campaign database" once per session launch
    /// (object identities change slowly; doing it once avoids any in-play cost).
    /// Writes the terminology + world snapshot to
    /// <c>&lt;save_data&gt;/&lt;campaign&gt;/storytools/</c>. Read-only — no game
    /// state is modified.
    /// </summary>
    public class ExportBehavior : CampaignBehaviorBase
    {
        public override void RegisterEvents()
        {
            CampaignEvents.OnSessionLaunchedEvent.AddNonSerializedListener(this, OnSessionLaunched);
        }

        public override void SyncData(IDataStore dataStore) { /* no persisted state */ }

        private void OnSessionLaunched(CampaignGameStarter starter)
        {
            var cfg = SettingsBridge.Current;
            if (cfg.AutoExport)
                ExportActions.ExportCampaignDatabase();
            if (cfg.AutoSyncEncyclopedia)
            {
                // Changed-files-only pass: on a fresh launch nothing has been
                // synced yet, so this covers every persona-bearing character; on
                // later loads it only revisits what the editor actually touched.
                EncyclopediaSync.Sync(force: false);
            }
        }

        internal static string ResolveFolder()
        {
            try
            {
                if (!FileContract.AiInfluenceInstalled) return null;
                Campaign c = Campaign.Current;
                if (c == null) return null;
                string uid = null;
                try { uid = c.UniqueGameId; } catch { /* ignore */ }
                string folder = FileContract.ResolveCampaignFolder(uid);
                if (string.IsNullOrEmpty(folder))
                    FileContract.Log("Export: could not resolve campaign folder.");
                return string.IsNullOrEmpty(folder) ? null : folder;
            }
            catch (Exception ex)
            {
                FileContract.Log("ExportBehavior.ResolveFolder ERROR: " + ex.Message);
                return null;
            }
        }
    }
}
