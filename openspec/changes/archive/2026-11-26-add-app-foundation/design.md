# Design

## Context

目前 repo 尚無應用程式程式碼與 capability specs；現有 `.gitignore` 已排除 `.env`、常見憑證、token、虛擬環境及暫存檔。動機與範圍見 `proposal.md`，可觀察行為見 `specs/app-foundation/spec.md`。

## Goals / Non-Goals

**Goals:**

- 建立單一套件的 Flask app factory 與三個可獨立掛載的模組邊界。
- 提供本機啟動、空白 SQLite 初始化、教師帳號管理與登入的共同底座。
- 讓 activities／quiz 不依賴 notes 的持久化細節，僅依固定函式契約讀取題目清單。

**Non-Goals:**

- 不實作 Guided Notes 解析、Google Sheets 讀寫或回填。動態辨識題號、合併題號列／小題與作答格，以及防止回填覆蓋標號，屬於後續 notes change；本 change 僅定義解析後清單的契約，不假設固定儲存格位置。
- 不實作課程、課堂、加入碼、學生身分、活動狀態、同步、提交、順位、結算及 CSV 匯出。

## Decisions

### 套件與應用程式建立

- 使用一個 Python 套件分出 `notes`、`activities`、`quiz` 子模組；共用 app factory 載入並驗證設定，建立 Flask app，再逐一註冊 Blueprint。
- Blueprint 路由各自留在所屬模組；登入、共用錯誤回應及資料庫初始化能力位於共用層。notes 本期只掛載空白頁。
- 替代方案：各模組各自建立 Flask app。此方案會造成設定與登入狀態分歧，且不利於本機整合，因此採單一 factory。

### 設定與啟動驗證

- `.env.example` 列出 `GUIDED_NOTES_SECRET_KEY`、`GUIDED_NOTES_DATABASE` 及 `GUIDED_NOTES_DEMO_CATALOG` 的範例值；README 說明在 Windows cmd 設定環境變數。程式只讀環境變數，不自行讀入或提交 `.env`。
- app 啟動時只要求 `GUIDED_NOTES_SECRET_KEY` 與 `GUIDED_NOTES_DATABASE`，缺漏時以清楚錯誤指出變數與設定方法。`NOTES_GOOGLE_CLIENT_SECRETS`、`NOTES_GOOGLE_TOKEN` 在 notes 實際執行 Google 功能時才驗證，以免尚未接入的功能阻擋共用 app 啟動。
- 替代方案：啟動時強制要求所有 Google 路徑。因本 change 不含匯入功能，這會無故阻擋登入及其他模組開發，故延遲檢查。

### SQLite 與命令列操作

- 共用資料庫路徑完全由 `GUIDED_NOTES_DATABASE` 指定。初始化指令建立所需 schema；教師建立指令使用同一設定連接該資料庫。開發與驗收明確使用全新空白資料庫（D14）。
- 命令列建立教師帳號時不接受密碼命令參數；執行後以不回顯提示輸入密碼並再次確認。兩次輸入不一致時中止且不新增資料，提示重新執行。成功時以密碼雜湊函式保存雜湊，不輸出或記錄明文密碼；登入以同一雜湊格式驗證。
- 替代方案：啟動時自動建表或自動建立預設教師。這會令測試及操作狀態不明確，且預設帳密有機敏風險，故採明確命令列操作。

### 教師登入、CSRF 與錯誤回應

- 登入狀態放在 Flask session cookie；secret key 必須來自 `GUIDED_NOTES_SECRET_KEY`。狀態變更請求一律驗證 CSRF token；登入錯誤使用相同一般訊息，不區分帳號不存在或密碼錯誤。
- 共用錯誤資料結構包含穩定的 `code` 與人類可讀的 `message`。HTML 頁面以適當狀態碼呈現；模組介面錯誤亦採用相同欄位，讓後續模組能穩定處理。
- 替代方案：把登入身分存於伺服器程序全域變數或只靠隱藏表單欄位。前者不能正確區分瀏覽器 session，後者不能保護狀態變更，故不採用。

### Blueprint 與首頁

- 首頁提供教師登入連結與顯示尚未開放的學生加入入口。教師頁面路由要求已登入，未登入時導向登入頁。notes、activities、quiz 各自暴露 Blueprint，app factory 統一掛載；後續模組可替換空白路由而不改 app 的整合方式。

### notes 題目清單契約

- notes 模組公開兩個函式：
- `list_available_catalogs(teacher_id)`：回傳該教師可存取的清單摘要陣列，每筆包含 `import_id`、`import_version`、`title`、`question_count`。
  - `get_catalog(teacher_id, import_id, import_version)`：以教師及清單識別值取得單一清單；成功回傳 `{import_id, import_version, questions}`。一般模式只允許該教師可存取的清單。
- `questions` 按來源順序排列；每題欄位為 `{question_id, display_number, type, items}`，其中 `type` 僅為 `single` 或 `group`。`items` 按來源順序排列，每個 item 為 `{item_id, label, order}`；`label` 是顯示標號，例如 `(1)`。單題恰有一個 item，題組有其所有有序作答項目。activities／quiz 只呼叫以上兩個函式，不讀 notes 資料表。
- 找不到指定組合或該教師無權存取時，`get_catalog` 以共用錯誤格式回報穩定代碼 `CATALOG_NOT_FOUND` 與一般說明訊息，不回傳其他教師清單，也不默默改用最新版本，確保活動可固定版本（D11）。
- 設定 `GUIDED_NOTES_DEMO_CATALOG=1` 時，列出與取得函式均提供同一份固定示範清單，任何已登入教師均可存取；清單至少含一題組與兩單題，且包含所有欄位。這是開發替身，不寫入 notes 持久化資料；真正匯入及清單儲存由後續 notes change 實作。
- 替代方案：由 activities／quiz 直接讀取 notes 資料表。此作法使模組耦合儲存 schema，notes 實作改動可能破壞消費者，因此採函式介面與固定資料結構。

### 機敏資料邊界

- 真正的 secret key、教師密碼及 OAuth 檔案／token 不放在原始碼、測試 fixture、文件或版本控制中。`.env.example` 只用明顯虛構的範例字串；Google 憑證與 token 存在 repo 外，以 `NOTES_GOOGLE_CLIENT_SECRETS`、`NOTES_GOOGLE_TOKEN` 指向。
- `.gitignore` 保持忽略 `.env`、憑證與 token 檔；README 指示使用者自行設定本機環境變數。測試使用臨時空白資料庫及臨時 secret，不引用個人檔案。

## Risks / Trade-offs

- [各模組對欄位名稱或排序定義理解不同] → 在 notes／activities 契約中固定欄位、型別、排序與錯誤語意，並以示範資料測試兩種讀取函式。
- [本機環境未設定 secret 或資料庫路徑而無法啟動] → 啟動錯誤列出確切變數及 Windows cmd 設定範例；README 由空白資料庫開始示範完整操作。
- [測試或示範設定誤用正式題目來源] → 示範清單為明確選擇的固定資料，僅在 `GUIDED_NOTES_DEMO_CATALOG=1` 開啟，不作為真實匯入資料。
- [將測試值誤提交為機敏設定] → 範例使用虛構值，測試用值只在執行期建立，並人工檢視版本控制檔案清單。
- [目前教師範圍依據 `teacher_id`，尚未區分教師的課程範圍] → 本 change 先以教師作為清單可見範圍；依 D15 加入課程範圍及其清單選取規則留待後續 change 擴充，屆時須維持函式契約的授權界線並更新介面。
- [共用骨架尚未驗證 Google OAuth 路徑是否位於 repo 外] → 本 change 僅檢查 Google 路徑環境變數是否存在；路徑位置與憑證檔驗證留待後續 notes change，由 notes 模組負責實作。

## Migration Plan

本 repo 尚無應用程式或既有資料可遷移。首次使用時，依 README 設定必要環境變數，指定新的空白 SQLite 路徑並執行初始化，再建立教師帳號。回復時可移除新建的本機資料庫並退回程式版本；不得要求或覆寫現存資料庫。

