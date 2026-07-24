using System;
using TaleWorlds.CampaignSystem;
using TaleWorlds.Core;
using TaleWorlds.MountAndBlade;

namespace AIInfluenceStoryMaster
{
    /// <summary>
    /// Entry point for "AI Influence: Story Master" — the mod core.
    ///
    /// Since v1.1.0 the module is the product's main body (the desktop editor
    /// ships inside its <c>Tool/</c> subfolder).  The core exports the campaign
    /// database, writes the game-state heartbeat, syncs the encyclopedia layout,
    /// and can launch the editor from MCM.  It never modifies AI Influence's
    /// campaign data.
    /// </summary>
    public class SubModule : MBSubModuleBase
    {
        public const string ModVersion = "1.2.0";

        // Real-time heartbeat throttle (seconds). Independent of the campaign
        // clock, so it stays fresh even when the game is paused.
        private const float HeartbeatIntervalSec = 3f;
        private float _hbAccum;

        protected override void OnSubModuleLoad()
        {
            base.OnSubModuleLoad();
            try
            {
                FileContract.Init();
                FileContract.Log("OnSubModuleLoad — Story Master v" + ModVersion
                                 + " loaded. game_base=" + FileContract.GameBase
                                 + " ai_save_data=" + FileContract.AiSaveDataDir
                                 + " ai_installed=" + FileContract.AiInfluenceInstalled);
                FileContract.WriteLoadMarker(ModVersion);
            }
            catch (Exception ex)
            {
                // Never let a companion-tool error disrupt the game.
                try { FileContract.Log("OnSubModuleLoad ERROR: " + ex); } catch { }
            }
        }

        protected override void OnBeforeInitialModuleScreenSetAsRoot()
        {
            base.OnBeforeInitialModuleScreenSetAsRoot();
            // Register the MCM menu now (all modules' OnSubModuleLoad have run, so
            // MCM's ModuleLoader is ready). No-op when MCM isn't installed.
            try { SettingsBridge.EnsureRegistered(); }
            catch (Exception ex) { try { FileContract.Log("MCM register skipped: " + ex.Message); } catch { } }
            // AI Influence's assembly is loaded by now (we load after it) — attach
            // the keep-our-encyclopedia-layout postfix.  Skips quietly without it.
            try
            {
                EncyclopediaSync.TryInstallPatch(new HarmonyLib.Harmony("AIInfluence_StoryMaster"));
            }
            catch (Exception ex) { try { FileContract.Log("Harmony patch skipped: " + ex.Message); } catch { } }
        }

        protected override void OnGameStart(Game game, IGameStarter starter)
        {
            base.OnGameStart(game, starter);
            try
            {
                if (game.GameType is Campaign && starter is CampaignGameStarter cs)
                {
                    cs.AddBehavior(new ExportBehavior());
                    FileContract.Log("Registered ExportBehavior.");
                }
            }
            catch (Exception ex)
            {
                try { FileContract.Log("OnGameStart ERROR: " + ex.Message); } catch { }
            }
        }

        protected override void OnApplicationTick(float dt)
        {
            base.OnApplicationTick(dt);
            // Throttled, real-time heartbeat (fires at main menu and in campaign,
            // paused or not). Keep this cheap — a small JSON write every ~3s.
            _hbAccum += dt;
            if (_hbAccum >= HeartbeatIntervalSec)
            {
                _hbAccum = 0f;
                if (SettingsBridge.Current.EnableHeartbeat) Heartbeat.Write();
            }
        }
    }
}
