# Proposal

## Why

目前 repo 只有專案說明與 OpenSpec 設定，尚無可供兩位組員整合功能的應用程式入口。先建立共用骨架、教師身分基礎與模組契約，讓後續 notes、activities、quiz changes 能在一致的設定、資料庫與 Blueprint 掛載方式上獨立實作。

## What Changes

- 建立 Python 3.13、Flask app factory 專案骨架，並提供 `notes`、`activities`、`quiz` Blueprint 接入點；notes 先提供空白頁。（本組自行決定；技術堆疊依 config.yaml）
- 從環境讀取必要設定 `GUIDED_NOTES_SECRET_KEY` 與 `GUIDED_NOTES_DATABASE`；缺漏時提供清楚說明。Google 路徑 `NOTES_GOOGLE_CLIENT_SECRETS`、`NOTES_GOOGLE_TOKEN` 僅在 notes 實際使用時檢查。（本組自行決定；名稱依 SpecKit 組）
- 提供 `.env.example`、SQLite 初始化指令、教師帳號建立指令、密碼雜湊、session cookie 登入與登出，以及狀態變更請求的 CSRF 保護。建立教師帳號時以不回顯提示輸入密碼並再次確認，不以命令參數傳入密碼。（D04；本組自行決定）
- 提供首頁的教師登入與尚未開放的學生加入入口、登入保護的教師頁，以及共用錯誤代碼與訊息格式。（D04；本組自行決定）
- 定義 notes 提供給 activities／quiz 的教師範圍題目清單函式契約：`list_available_catalogs(teacher_id)` 與 `get_catalog(teacher_id, import_id, import_version)`；清單摘要含 `import_id`、`import_version`、`title`、`question_count`，並提供可切換且任何已登入教師可存取的示範清單。（D10、D11；本組自行決定）
- 加入 pytest 自動驗收與 README 的 Windows cmd 操作步驟；驗收使用新的空白資料庫。（D14；本組自行決定）

### Out of Scope

本 change 不實作下列功能；由後續 change 負責：課程、課堂、加入碼、學生加入、活動與階段、同步、作答提交、順位、結算、Google Sheets 匯入與回填、CSV 匯出。

## Capabilities

### New Capabilities

- `app-foundation`: 共用應用程式設定、資料庫初始化、教師登入、錯誤格式、Blueprint 掛載點及 notes 題目清單介面。

### Modified Capabilities

無；目前沒有既有 specs。

## Impact

- 新增一個 Python 套件與 Flask app factory、設定驗證、SQLite schema 初始化、教師認證、Blueprint、模板與題目清單介面。
- 新增 pytest 測試與 `.env.example`，更新 README；執行期依賴 Flask，測試依賴 pytest。
- notes、activities、quiz 透過 Blueprint 掛載；activities 與 quiz 僅透過 notes 公開函式並提供 `teacher_id` 取得其可存取的題目清單，不直接查詢 notes 資料表。
- 機敏設定不得有程式碼預設值；實際 secret、教師密碼及 Google 憑證不得進入 repo。Google 憑證檔路徑由環境變數指定並留待 notes 使用時檢查。
