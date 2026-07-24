using System.Runtime.CompilerServices;
using AIInfluenceStoryMaster.Settings;

namespace AIInfluenceStoryMaster
{
    /// <summary>
    /// Soft-dependency accessor for the MCM settings.  MCM is optional: when it
    /// isn't installed, our DLL must still load and run on defaults.
    ///
    /// The trick is JIT isolation.  A method that references
    /// <see cref="StoryMasterSettings"/> (which derives from an MCM type) forces
    /// the MCM assembly to load when that method is JIT-compiled.  So every such
    /// reference lives in a separate <c>[MethodImpl(NoInlining)]</c> method that
    /// is only ever *called* after <see cref="McmLoaded"/> confirms MCM is
    /// present — the gating properties themselves never name an MCM type, so they
    /// JIT (and run) fine without MCM.
    /// </summary>
    internal static class SettingsBridge
    {
        internal struct Cfg
        {
            public bool AutoExport;              // auto-export campaign database on session launch
            public bool AutoSyncEncyclopedia;    // refresh encyclopedia text on session launch
            public bool EnableHeartbeat;
        }

        private static Cfg Defaults => new Cfg
        {
            AutoExport = true,
            AutoSyncEncyclopedia = true,
            EnableHeartbeat = true,
        };

        private static bool? _mcm;

        /// <summary>True when MCM is loaded. Detected via type-name lookup across
        /// already-loaded assemblies (no compile-time MCM reference, so this is
        /// safe to JIT without MCM).</summary>
        private static bool McmLoaded
        {
            get
            {
                if (_mcm.HasValue) return _mcm.Value;
                bool found = false;
                try
                {
                    // AccessTools.TypeByName scans loaded assemblies without
                    // triggering AssemblyResolve (the §21-safe detection).
                    found = HarmonyLib.AccessTools.TypeByName(
                        "MCM.Abstractions.Base.Global.AttributeGlobalSettings`1") != null;
                }
                catch { found = false; }
                _mcm = found;
                return found;
            }
        }

        /// <summary>Current effective config — MCM values when present, else defaults.</summary>
        public static Cfg Current => McmLoaded ? ReadAll() : Defaults;

        /// <summary>Touch the settings once so MCM registers the menu entry.
        /// No-op (and never loads MCM) when MCM is absent.</summary>
        public static void EnsureRegistered()
        {
            if (McmLoaded) ForceRegister();
        }

        // ── MCM-touching methods: only called when McmLoaded is true ────────

        [MethodImpl(MethodImplOptions.NoInlining)]
        private static Cfg ReadAll()
        {
            var s = StoryMasterSettings.Instance;
            if (s == null) return Defaults;
            return new Cfg
            {
                AutoExport = s.AutoExport,
                AutoSyncEncyclopedia = s.AutoSyncEncyclopedia,
                EnableHeartbeat = s.EnableHeartbeat,
            };
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void ForceRegister()
        {
            var _ = StoryMasterSettings.Instance;
        }
    }
}
