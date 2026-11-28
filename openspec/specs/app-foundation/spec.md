# app-foundation Specification

## Purpose

提供課堂搶答系統可供後續模組接入的共用應用程式能力，包含教師登入、資料庫啟動、模組掛載與 notes 題目清單契約。

## Requirements

### Requirement: 必要環境設定
應用程式 SHALL 從環境讀取 `GUIDED_NOTES_SECRET_KEY` 與 `GUIDED_NOTES_DATABASE`，不得以程式碼內的機敏預設值取代；缺少設定時 SHALL 清楚指出變數名稱與設定方式。（本組自行決定；名稱與 SpecKit 組一致）

#### Scenario: 必要設定完整
- **WHEN** 啟動時兩個必要環境變數皆已設定
- **THEN** 應用程式使用指定 secret key 與資料庫路徑啟動

#### Scenario: 缺少必要設定
- **WHEN** 啟動時缺少任一必要環境變數
- **THEN** 啟動失敗訊息指出缺少的變數名稱及設定方式

#### Scenario: Google 憑證延遲檢查
- **WHEN** 應用程式啟動但尚未執行 notes 的 Google 功能，且未設定 `NOTES_GOOGLE_CLIENT_SECRETS` 或 `NOTES_GOOGLE_TOKEN`
- **THEN** 應用程式仍可啟動，而在 notes 實際使用 Google 功能時才回報缺少的憑證路徑設定

### Requirement: 空白資料庫初始化
系統 SHALL 提供可對指定 SQLite 路徑初始化 schema 的指令，以供開發與驗收使用新的空白資料庫。（D14；本組自行決定）

#### Scenario: 初始化新的空白資料庫
- **WHEN** 使用者將 `GUIDED_NOTES_DATABASE` 指向尚不存在的資料庫並執行初始化指令
- **THEN** 指令建立資料庫及共用 schema，且可回報初始化完成

### Requirement: 教師帳號建立與密碼儲存
系統 SHALL 透過命令列建立教師帳號，密碼 SHALL 以不回顯提示輸入並再次確認，不得由命令參數提供；系統 SHALL 以不可逆密碼雜湊儲存密碼。（D04；本組自行決定）

#### Scenario: 建立教師帳號
- **WHEN** 使用者透過命令列提供教師帳號，並依不回顯提示輸入兩次相同密碼
- **THEN** 帳號可供登入，資料庫保存的密碼欄位不是原始密碼

#### Scenario: 密碼確認不一致
- **WHEN** 使用者兩次輸入的密碼不一致
- **THEN** 指令拒絕建立帳號並提示重新執行，資料庫不新增任何資料

### Requirement: 教師登入與登出
系統 SHALL 以 session cookie 保存教師登入狀態，並在登出後使登入狀態失效。（D04；本組自行決定）

#### Scenario: 正確密碼登入
- **WHEN** 教師以已建立帳號及正確密碼提交登入
- **THEN** 系統建立登入狀態並導向教師頁

#### Scenario: 錯誤密碼登入
- **WHEN** 教師以無效帳號或錯誤密碼提交登入
- **THEN** 系統拒絕登入並顯示不透露帳號是否存在的一般錯誤訊息

#### Scenario: 登出
- **WHEN** 已登入教師提出登出請求
- **THEN** 系統清除登入狀態，後續教師頁請求視為未登入

### Requirement: 教師頁面存取保護
系統 SHALL 限制教師頁面僅供已登入教師存取。（D04）

#### Scenario: 未登入導向登入
- **WHEN** 未登入使用者存取教師頁面
- **THEN** 系統導向教師登入頁

### Requirement: 狀態變更請求的 CSRF 保護
所有會改變狀態的請求 SHALL 驗證 CSRF token。（本組自行決定）

#### Scenario: 缺少或無效 CSRF token
- **WHEN** 狀態變更請求未提供有效 CSRF token
- **THEN** 系統拒絕該請求且不執行狀態變更

### Requirement: 共用頁面與 Blueprint 掛載點
系統 SHALL 提供教師登入與學生加入兩個首頁入口，並允許 notes、activities、quiz 各自以 Blueprint 接入；本 change 的學生加入入口 SHALL 顯示尚未開放，notes SHALL 提供空白掛載頁。（D04；本組自行決定）

#### Scenario: 首頁入口顯示
- **WHEN** 使用者開啟首頁
- **THEN** 頁面顯示教師登入入口與尚未開放的學生加入入口

#### Scenario: 三個模組可掛載
- **WHEN** 建立應用程式並註冊 notes、activities、quiz Blueprint
- **THEN** 三個模組路由均可由應用程式提供，且 notes 顯示空白頁

### Requirement: notes 題目清單介面

notes SHALL 提供 `list_available_catalogs(teacher_id)` 及 `get_catalog(teacher_id, import_id, import_version)` 函式，先確認 `teacher_id` 對應資料庫中存在的教師，再回傳該教師可存取的清單；無此教師時 SHALL 以 `TEACHER_REQUIRED` 拒絕。示範模式允許所有已存在的教師以這兩個函式存取示範清單。課程活動的版本選用與文字交付 SHALL 使用 Notes 提供的課程範圍查詢。activities 與 quiz SHALL 透過 Notes 公開查詢存取清單，禁止直接讀取 Notes 資料表。（D10、D11、D15、D19；函式名稱與結構為本組契約）

#### Scenario: 列出教師可存取清單
- **WHEN** 以已登入教師的 `teacher_id` 呼叫 `list_available_catalogs(teacher_id)`
- **THEN** 僅回傳該教師可存取的清單摘要，且每筆摘要包含 `import_id`、`import_version`、`title` 與 `question_count`

#### Scenario: 取得教師可存取的指定清單
- **WHEN** 以已登入教師的 `teacher_id` 及存在且可存取的 `import_id`、`import_version` 呼叫 `get_catalog(teacher_id, import_id, import_version)`
- **THEN** 回傳固定結構，包含 `import_id`、`import_version` 及依來源順序排列的題目

#### Scenario: 阻擋其他教師的清單
- **WHEN** 教師以自己的 `teacher_id` 取得另一位教師的清單
- **THEN** 函式以共用錯誤格式回報清單不可用，且不洩漏該清單是否存在

#### Scenario: 拒絕不存在的教師
- **WHEN** `teacher_id` 不對應資料庫中的教師，且該值呼叫任一題目清單函式
- **THEN** 函式以 `TEACHER_REQUIRED` 錯誤代碼拒絕請求

#### Scenario: 題目及作答項目結構
- **WHEN** 呼叫既有單一清單函式取得含單題與題組的清單
- **THEN** 每題包含 `question_id`、`display_number`、`type`（`single` 或 `group`）與有序 `items`；每個 item 包含 `item_id`、`label` 及 `order`，且單題恰有一個 item

#### Scenario: 未知清單識別或版本
- **WHEN** 以 `teacher_id` 呼叫既有單一清單函式時 `import_id` 與 `import_version` 無對應可存取清單
- **THEN** 函式以 `CATALOG_NOT_FOUND` 回報，不回傳其他版本清單

#### Scenario: 啟用示範清單
- **WHEN** 設定 `GUIDED_NOTES_DEMO_CATALOG=1` 且任何已存在的教師以既有教師範圍介面列出或取得示範清單
- **THEN** 回傳包含至少一個題組與兩個單題的固定結構示範清單，題目及 items 順序明確

#### Scenario: 存取課程的固定講義版本
- **WHEN** activities 為教師選定的課程查詢講義，或為課程活動載入指定版本的題目文字
- **THEN** Notes 先驗證該教師的課程權限，只交付該課程可存取的正式版本與該版本的題目資料
- **AND** 既有教師範圍查詢的簽章、回傳欄位及錯誤維持相容

### Requirement: 共用錯誤回應格式
系統對外回報錯誤 SHALL 提供可機器辨識的錯誤代碼與供使用者理解的訊息。（本組自行決定）

#### Scenario: 發生可預期錯誤
- **WHEN** 請求或模組介面遇到可預期錯誤
- **THEN** 回應包含錯誤代碼與訊息，且格式一致

### Requirement: 機敏資料不進入 repo
系統與操作文件 SHALL 不包含實際 secret key、密碼或 Google 憑證／token；範例環境檔 SHALL 只含虛構範例值，Google 憑證檔 SHALL 位於 repo 外並以環境變數指定路徑。（本組自行決定；符合 config.yaml 硬性限制）

#### Scenario: 檢查範例檔與版本控制內容
- **WHEN** 檢查 `.env.example` 及 repo 追蹤的檔案
- **THEN** 範例只有示範值，repo 不含真實 secret、密碼、OAuth client 檔或 token
