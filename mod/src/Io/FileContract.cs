using System;
using System.IO;
using System.Text;
// NOTE: do NOT `using TaleWorlds.Engine;` — it defines a `Path` type that
// collides with System.IO.Path. Utilities is referenced fully-qualified below.

namespace AIInfluenceStoryMaster
{
    /// <summary>
    /// Resolves the shared file paths between the Story Master mod and the
    /// external Story Tools application, and provides atomic writes + logging.
    ///
    /// Contract (mod → tool, one-way; the tool only reads):
    ///   &lt;AIInfluence save_data&gt;/storytools/heartbeat.json          (global)
    ///   &lt;AIInfluence save_data&gt;/&lt;campaign_id&gt;/storytools/...   (per-campaign)
    ///
    /// AI Influence stores its save_data directly under its own module folder
    /// (Modules/AIInfluence/save_data), so we locate it as a sibling module
    /// via the game base path — no dependency on AI Influence's internals.
    /// </summary>
    internal static class FileContract
    {
        public const int SchemaVersion = 1;

        private static bool _initialized;
        private static string _gameBase;
        private static string _ourModuleDir;
        private static string _aiSaveDataDir;
        private static string _logFile;

        public static string GameBase => _gameBase;
        public static string OurModuleDir => _ourModuleDir;
        public static string AiSaveDataDir => _aiSaveDataDir;
        public static bool AiInfluenceInstalled =>
            !string.IsNullOrEmpty(_aiSaveDataDir) && Directory.Exists(_aiSaveDataDir);

        public static void Init()
        {
            if (_initialized) return;
            _gameBase = SafeBasePath();
            string modules = Path.Combine(_gameBase, "Modules");
            _ourModuleDir = Path.Combine(modules, "AIInfluence_StoryMaster");
            _aiSaveDataDir = Path.Combine(modules, "AIInfluence", "save_data");

            string logDir = Path.Combine(_ourModuleDir, "logs");
            try { Directory.CreateDirectory(logDir); } catch { /* ignore */ }
            _logFile = Path.Combine(logDir, "storymaster.log");
            _initialized = true;
        }

        private static string SafeBasePath()
        {
            // Resolve to an ABSOLUTE path: GetBasePath() can return a relative
            // path (observed "../.." on 1.4.6). GetFullPath anchors it to the
            // current working directory at init time (the game bin dir), so the
            // path stays valid even if the CWD changes later during play.
            try
            {
                string p = TaleWorlds.Engine.Utilities.GetBasePath();
                if (!string.IsNullOrEmpty(p))
                    return Path.GetFullPath(p.TrimEnd('/', '\\'));
            }
            catch { /* fall through */ }
            try
            {
                return Path.GetFullPath((AppDomain.CurrentDomain.BaseDirectory ?? ".").TrimEnd('/', '\\'));
            }
            catch { return "."; }
        }

        /// <summary>Global storytools dir (heartbeat etc.).</summary>
        public static string GlobalStorytoolsDir()
        {
            string d = Path.Combine(_aiSaveDataDir, "storytools");
            Directory.CreateDirectory(d);
            return d;
        }

        /// <summary>Per-campaign storytools dir (terminology / world snapshot).</summary>
        public static string CampaignStorytoolsDir(string campaignId)
        {
            string d = Path.Combine(_aiSaveDataDir, campaignId, "storytools");
            Directory.CreateDirectory(d);
            return d;
        }

        /// <summary>
        /// Resolve the save_data subfolder for the active campaign: prefer a
        /// folder named exactly <paramref name="uniqueGameId"/> when it exists,
        /// otherwise the most-recently-written folder (AI Influence writes to the
        /// active campaign constantly). Returns null when nothing is found.
        /// </summary>
        public static string ResolveCampaignFolder(string uniqueGameId)
        {
            try
            {
                if (!string.IsNullOrEmpty(uniqueGameId))
                {
                    if (Directory.Exists(Path.Combine(_aiSaveDataDir, uniqueGameId)))
                        return uniqueGameId;
                }
                return NewestCampaignFolder();
            }
            catch { return null; }
        }

        /// <summary>
        /// save_data subfolders that are never campaigns: our own contract dir and
        /// AI Influence's own scratch dirs. `_portrait_tmp` is the Content Editor's
        /// portrait capture buffer (6.0+) — it is written constantly while the
        /// editor is open and would otherwise win the newest-mtime race.
        /// </summary>
        private static readonly string[] ReservedFolders =
        {
            "storytools",
            "_portrait_tmp",
        };

        private static bool IsReservedFolder(string name)
        {
            foreach (string r in ReservedFolders)
                if (string.Equals(name, r, StringComparison.OrdinalIgnoreCase))
                    return true;
            return false;
        }

        /// <summary>
        /// A real campaign folder always carries AI Influence campaign data: the
        /// diplomacy bundle or the per-campaign prompts tree. Checking for these
        /// keeps unknown future scratch folders out without needing to name them.
        /// </summary>
        private static bool LooksLikeCampaignFolder(string fullPath)
        {
            try
            {
                if (File.Exists(Path.Combine(fullPath, "aiinfluence_campaign_diplomacy.json")))
                    return true;
                return Directory.Exists(Path.Combine(fullPath, "prompts"));
            }
            catch { return false; }
        }

        /// <summary>
        /// Name of the most-recently-written campaign subfolder under save_data
        /// (AI Influence writes constantly to the active campaign during play, so
        /// the newest-mtime folder is the live one). Reserved and non-campaign
        /// folders are skipped; when nothing validates we fall back to the newest
        /// non-reserved folder rather than reporting nothing. Returns null if none.
        /// </summary>
        public static string NewestCampaignFolder()
        {
            try
            {
                if (!Directory.Exists(_aiSaveDataDir)) return null;
                DirectoryInfo newest = null;
                DirectoryInfo newestUnvalidated = null;
                foreach (var d in new DirectoryInfo(_aiSaveDataDir).GetDirectories())
                {
                    if (IsReservedFolder(d.Name)) continue;
                    if (newestUnvalidated == null || d.LastWriteTimeUtc > newestUnvalidated.LastWriteTimeUtc)
                        newestUnvalidated = d;
                    if (!LooksLikeCampaignFolder(d.FullName)) continue;
                    if (newest == null || d.LastWriteTimeUtc > newest.LastWriteTimeUtc)
                        newest = d;
                }
                DirectoryInfo pick = newest ?? newestUnvalidated;
                return pick != null ? pick.Name : null;
            }
            catch { return null; }
        }

        /// <summary>
        /// M0 proof: write a load marker so we (and the user) can confirm the
        /// mod loaded and resolved AI Influence's save_data path correctly —
        /// even before any campaign is loaded.
        /// </summary>
        public static void WriteLoadMarker(string version)
        {
            if (!AiInfluenceInstalled)
            {
                Log("AIInfluence save_data NOT found at: " + _aiSaveDataDir + " — load marker skipped.");
                return;
            }
            string path = Path.Combine(GlobalStorytoolsDir(), "_storymaster_loaded.json");
            var sb = new StringBuilder();
            sb.Append("{\n");
            sb.Append("  \"schema_version\": ").Append(SchemaVersion).Append(",\n");
            sb.Append("  \"mod\": \"AIInfluence_StoryMaster\",\n");
            sb.Append("  \"mod_version\": \"").Append(Escape(version)).Append("\",\n");
            sb.Append("  \"game_base\": \"").Append(Escape(_gameBase)).Append("\",\n");
            sb.Append("  \"ai_influence_save_data\": \"").Append(Escape(_aiSaveDataDir)).Append("\",\n");
            sb.Append("  \"wrote_at\": \"").Append(DateTime.UtcNow.ToString("o")).Append("\"\n");
            sb.Append("}\n");
            AtomicWrite(path, sb.ToString());
            Log("Wrote load marker: " + path);
        }

        /// <summary>Atomic write: tmp file then replace, UTF-8 without BOM.</summary>
        public static void AtomicWrite(string path, string content)
        {
            string tmp = path + ".tmp";
            File.WriteAllText(tmp, content, new UTF8Encoding(false));
            if (File.Exists(path)) File.Delete(path);
            File.Move(tmp, path);
        }

        public static void Log(string msg)
        {
            try
            {
                File.AppendAllText(_logFile ?? "storymaster.log",
                    DateTime.UtcNow.ToString("o") + "  " + msg + Environment.NewLine,
                    new UTF8Encoding(false));
            }
            catch { /* logging must never throw */ }
        }

        private static string Escape(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }
    }
}
