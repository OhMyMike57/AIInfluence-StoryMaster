# AI Influence: Story Master - Connector（連接器）

桌面工具「AI Influence: Story Master／AI效應：故事大師」的遊戲端連接器
（Bannerlord 1.4.x，.NET Framework 4.7.2）。
架構原始計畫：`../docs/封存/Phase7連接器計畫_已完成.md`；
專案狀態單一真相源：`../docs/專案總覽.html`。

- **對外名稱**：AI Influence: Story Master - Connector／AI效應：故事大師-連接器
- **模組 Id**：`AIInfluence_StoryMaster`（凍結識別碼，永不更名）
- **定位**：唯讀觀測者。只讀遊戲、只寫給工具用的 JSON，**不改任何遊戲狀態**。
- **功能**：心跳檔（精準遊戲狀態偵測）＋ 戰役名詞庫自動匯出（含定居點；
  另有 MCM「匯出 ID 資料」手動匯出）。

## 源碼與部署副本

**這裡（`mod/`）是唯一源碼**。repo 根目錄的 `companion_mod/` 是建置產物副本
（工具「一鍵安裝連接器」用的 payload），由 `build_and_deploy.ps1` 自動回寫，
**不要手改**。

## 建置

```
dotnet build -c Release
```

輸出：`bin/Win64_Shipping_Client/AIInfluence_StoryMaster.dll`。
（遊戲路徑預設 `E:\SteamLibrary\...`；用 `-p:BannerlordPath="..."` 覆寫。）

## 建置並部署（開發用）

```
.\build_and_deploy.ps1
```

一次完成：`dotnet build` → 部署到遊戲 `Modules/AIInfluence_StoryMaster/` →
回寫 `companion_mod/` payload。之後在啟動器勾選模組，載入順序排在
**AI Influence 與 Harmony 之後**。

版本號來源：`SubModule.xml` 的 `<Version>` 與 `module_version.txt`（兩處同步改）。

## 路徑契約

連接器把給工具讀的檔案寫到 **AI 效應自己的 save_data**（在其模組資料夾下）：

```
<game>/Modules/AIInfluence/save_data/storytools/               # 全域（heartbeat 等）
<game>/Modules/AIInfluence/save_data/<campaign_id>/storytools/ # per-campaign（名詞庫等）
```

連接器自身 log：`<game>/Modules/AIInfluence_StoryMaster/logs/storymaster.log`。

## 散佈方式

不單獨上傳 Nexus。連接器 payload 隨工具打包（`StoryMaster.spec` 的
`companion_mod/` datas），玩家在工具「設定」分頁一鍵安裝／更新。
