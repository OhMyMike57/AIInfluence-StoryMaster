using System;
using TaleWorlds.Core;
using TaleWorlds.Library;
using TaleWorlds.Localization;

namespace AIInfluenceStoryMaster.Settings
{
    /// <summary>
    /// The "export campaign database" action — writes the terminology (objects +
    /// metadata) and the world snapshot together.  Used both by the session-launch
    /// auto-export and the MCM manual button.  Read-only; needs a loaded campaign.
    /// </summary>
    internal static class ExportActions
    {
        public static void ExportCampaignDatabase()
        {
            try
            {
                string folder = ExportBehavior.ResolveFolder();
                if (string.IsNullOrEmpty(folder))
                {
                    Info("{=StoryMaster_Msg_NoCampaign}Story Master: load a campaign first");
                    return;
                }
                TerminologyExport.Export(folder);
                WorldSnapshot.Export(folder);
                Info("{=StoryMaster_Msg_Updated}Story Master: database updated");
            }
            catch (Exception ex)
            {
                try { FileContract.Log("Manual export ERROR: " + ex); } catch { }
                Info("{=StoryMaster_Msg_Failed}Story Master: update failed, see log");
            }
        }

        /// <summary>
        /// Refresh the in-game encyclopedia from the character files, so persona
        /// edits made in the external editor show up even for characters the
        /// player has not interacted with this session.  The manual (MCM button)
        /// run forces a full pass; the session-launch pass only revisits files
        /// changed since the previous sync.
        /// </summary>
        public static void SyncEncyclopediaNow()
        {
            try
            {
                int n = EncyclopediaSync.Sync(force: true);
                if (n < 0)
                {
                    Info("{=StoryMaster_Msg_NoCampaign}Story Master: load a campaign first");
                    return;
                }
                InfoCount("{=StoryMaster_Msg_EncSynced}Story Master: encyclopedia refreshed ({COUNT} characters)", n);
            }
            catch (Exception ex)
            {
                try { FileContract.Log("Manual encyclopedia sync ERROR: " + ex); } catch { }
                Info("{=StoryMaster_Msg_Failed}Story Master: update failed, see log");
            }
        }

        /// <summary>
        /// Put every encyclopedia page Story Master rewrote back to its original.
        ///
        /// Needed because <c>Hero.EncyclopediaText</c> lives in the save file: simply
        /// switching the feature off leaves the rewritten pages behind forever.
        /// See <see cref="EncyclopediaSync.RestoreOriginals"/> for the three tiers.
        /// </summary>
        public static void RestoreEncyclopediaNow()
        {
            try
            {
                int n = EncyclopediaSync.RestoreOriginals();
                if (n < 0)
                {
                    Info("{=StoryMaster_Msg_NoCampaign}Story Master: load a campaign first");
                    return;
                }
                InfoCount("{=StoryMaster_Msg_EncRestored}Story Master: {COUNT} encyclopedia page(s) restored", n);
            }
            catch (Exception ex)
            {
                try { FileContract.Log("Encyclopedia restore ERROR: " + ex); } catch { }
                Info("{=StoryMaster_Msg_Failed}Story Master: update failed, see log");
            }
        }

        /// <summary>
        /// Launch the desktop editor that ships in the module's <c>Tool/</c>
        /// subfolder.  Since v1.1.0 the module is the main body and the editor
        /// lives inside it, so the path is fixed relative to the module root.
        /// </summary>
        public static void OpenEditor()
        {
            try
            {
                string exe = System.IO.Path.Combine(
                    FileContract.OurModuleDir ?? "", "Tool", "StoryMaster.exe");
                if (!System.IO.File.Exists(exe))
                {
                    Info("{=StoryMaster_Msg_NoEditor}Story Master: editor not found (Tool folder is missing from the module)");
                    return;
                }
                var psi = new System.Diagnostics.ProcessStartInfo
                {
                    FileName = exe,
                    WorkingDirectory = System.IO.Path.GetDirectoryName(exe),
                    UseShellExecute = true,
                };
                System.Diagnostics.Process.Start(psi);
                Info("{=StoryMaster_Msg_EditorOpened}Story Master: editor launched");
            }
            catch (Exception ex)
            {
                try { FileContract.Log("OpenEditor ERROR: " + ex); } catch { }
                Info("{=StoryMaster_Msg_Failed}Story Master: update failed, see log");
            }
        }

        /// <summary>Show a keyed message carrying a {COUNT} placeholder.</summary>
        private static void InfoCount(string keyed, int count)
        {
            try
            {
                var to = new TextObject(keyed);
                to.SetTextVariable("COUNT", count);
                InformationManager.DisplayMessage(new InformationMessage(to.ToString()));
            }
            catch { /* not in a state to show messages */ }
        }

        /// <summary>Show an in-game message. The argument is a localization-keyed
        /// string ("{=id}English fallback"); TextObject resolves it to the active
        /// game language (falling back to the inline English when no string file
        /// covers that language), matching the MCM settings' localization.</summary>
        private static void Info(string keyed)
        {
            try
            {
                string msg = new TextObject(keyed).ToString();
                InformationManager.DisplayMessage(new InformationMessage(msg));
            }
            catch { /* not in a state to show messages */ }
        }
    }
}
