using System;
using System.Collections.Generic;
using System.IO;
using System.Xml;

namespace AIInfluenceStoryMaster
{
    /// <summary>
    /// Recovers the hand-written encyclopedia text of pre-authored heroes from the
    /// module XMLs that define them.
    ///
    /// Why this exists: <c>Hero.EncyclopediaText</c> is serialised into the save, so
    /// once Story Master (or AI Influence) has overwritten a page the original is
    /// gone from live data. For heroes declared in XML the source is still on disk —
    /// <c>Hero.Deserialize</c> reads it from a <c>text=</c> attribute
    /// (<c>Hero.cs</c>, the ``EncyclopediaText = node.Attributes["text"] …`` line) —
    /// so parsing those files back gives an authored original that no amount of
    /// regeneration could reproduce.
    ///
    /// Heroes with no <c>text=</c> attribute (the majority — the game generates their
    /// sentence at runtime) simply do not appear in the map; the caller falls back to
    /// <c>Hero.SetHeroEncyclopediaTextAndLinks</c>.
    ///
    /// Deliberately forgiving: any unreadable file, missing folder or malformed node
    /// is skipped. A failure here only costs restore precision, so it must never
    /// throw into the caller.
    /// </summary>
    internal static class XmlEncyclopediaText
    {
        /// <summary>Files that declare heroes. Names vary by module, so we match on
        /// content (a &lt;Hero&gt; element with an id) rather than a fixed list.</summary>
        private const string ModuleDataDir = "ModuleData";

        private static Dictionary<string, string> _cache;

        /// <summary>StringId → authored encyclopedia text, across every installed
        /// module. Scanned once per session.</summary>
        public static Dictionary<string, string> Load()
        {
            if (_cache != null) return _cache;
            _cache = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            try
            {
                string modules = ModulesRoot();
                if (modules == null || !Directory.Exists(modules)) return _cache;

                foreach (string module in Directory.GetDirectories(modules))
                {
                    string data = Path.Combine(module, ModuleDataDir);
                    if (!Directory.Exists(data)) continue;
                    foreach (string file in Directory.GetFiles(data, "*.xml",
                                                               SearchOption.AllDirectories))
                        ScanFile(file);
                }
                FileContract.Log("XmlEncyclopediaText: " + _cache.Count
                                 + " authored hero page(s) found in module XML.");
            }
            catch (Exception ex)
            {
                FileContract.Log("XmlEncyclopediaText.Load ERROR: " + ex.Message);
            }
            return _cache;
        }

        private static string ModulesRoot()
        {
            try
            {
                // OurModuleDir is "<game>\Modules\AIInfluence_StoryMaster".
                string ours = FileContract.OurModuleDir;
                if (string.IsNullOrEmpty(ours)) return null;
                return Path.GetDirectoryName(ours);
            }
            catch { return null; }
        }

        private static void ScanFile(string path)
        {
            try
            {
                // A quick substring test first: most ModuleData XMLs are equipment,
                // items or localisation, and parsing every one of them would cost far
                // more than reading the bytes twice.
                string raw = File.ReadAllText(path);
                if (raw.IndexOf("<Hero", StringComparison.OrdinalIgnoreCase) < 0) return;
                if (raw.IndexOf("text=", StringComparison.OrdinalIgnoreCase) < 0) return;

                var doc = new XmlDocument();
                doc.LoadXml(raw);
                XmlNodeList nodes = doc.GetElementsByTagName("Hero");
                if (nodes == null) return;
                foreach (XmlNode node in nodes)
                {
                    if (node == null || node.Attributes == null) continue;
                    XmlAttribute idAttr = node.Attributes["id"];
                    XmlAttribute textAttr = node.Attributes["text"];
                    if (idAttr == null || textAttr == null) continue;
                    string id = (idAttr.Value ?? "").Trim();
                    string text = textAttr.Value ?? "";
                    if (id.Length == 0 || text.Trim().Length == 0) continue;
                    // First module wins: load order means an earlier module's value is
                    // the one the game used, and overwriting it here would restore text
                    // the player never saw.
                    if (!_cache.ContainsKey(id)) _cache[id] = text;
                }
            }
            catch
            {
                /* unreadable or not well-formed — skip, precision only */
            }
        }
    }
}
