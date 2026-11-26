# Design

## Context

Foundation 已合併，提供 Flask app factory、教師登入、CSRF、SQLite 及 `/notes`。目前 Notes 有占位頁、既有講義查詢函式、示範資料與 OAuth 路徑檢查。正式講義儲存、課程授權及活動結算快照仍待實作。參照 [Foundation 主規格](../../specs/app-foundation/spec.md)、[提案](proposal.md)、[差異規格](specs/guided-notes/spec.md)。

## Goals / Non-Goals

- **Goals**　以可獨立測試的解析、版本保存及回填元件分離外部 Sheets 存取；用模擬的 A／B 介面驗證資料交接。
- **Non-Goals**　由 B 管理教師登入、課堂狀態、提交、順位及結算。A 只向 B 取得授權與結算資料。CSV、教師 Google 登入、Drive Picker 與講義移除見提案範圍外。

## Decisions

### Blueprint、教師權限與共用 SQLite（D04、D11、D15）

- 在 `guided_notes.notes.bp` 新增教師匯入、預覽、保存及回填路由。沿用 `create_app()` 既有的 `/notes` 掛載與占位頁。
- 教師頁沿用 `pages.teacher_required` 的登入導向。操作所用的 `teacher_id` 取自 Flask session，由登入流程設定。路由與查詢仍需確認教師在 `teachers` 表存在，並檢查目標資料的存取權。課程及活動的授權接點待 B 對齊；缺少相應授權時不執行操作。
- 保存與回填沿用全域 CSRF。表單提交 `csrf_token`，前端請求可使用 `X-CSRF-Token`。沿用共用 `AppError` 與 HTTP 錯誤回應的 `error.code`、`error.message`。
- 用 `guided_notes.db.get_db()` 存取 `GUIDED_NOTES_DATABASE` 指向的同一 SQLite 資料庫。在既有 `init-db` 流程中初始化 Notes 所需資料表，保留教師與既有資料。正式持久化接到 `_catalogs_for_teacher()`，先依教師授權限縮可讀清單，讓其他模組繼續透過兩個公開查詢函式存取。
- Foundation 的 `GUIDED_NOTES_DEMO_CATALOG=1` 只走示範清單分支，所有有效教師皆可讀取示範資料。正式匯入、持久化、版本與隔離驗收一律設為 `0` 或維持未設定，並與示範清單的相容測試分開。

### 授權與 Sheets 存取（本組技術決定，R02、R10）

- 按專案設定使用官方 `google-api-python-client`、Desktop OAuth 與 `https://www.googleapis.com/auth/spreadsheets`。以獨立的本機授權指令執行互動流程。HTTP 處理只讀取或非互動更新既有憑證，不能使用時回傳重新授權提示。前一輪評估的網頁 OAuth 及 Picker 留給另案。
- 沿用 `google_credentials_paths()`，只在 Notes 執行 Google 功能時檢查 `NOTES_GOOGLE_CLIENT_SECRETS` 與 `NOTES_GOOGLE_TOKEN`，缺少路徑維持 `GOOGLE_CREDENTIALS_REQUIRED`。清單查詢只讀 SQLite。OAuth 檔案放在 repo 外；Flask 讀取 `GUIDED_NOTES_SECRET_KEY`，教師密碼由既有 CLI 不回顯輸入並在 SQLite 儲存雜湊。文件採占位值，回應與日誌不記錄機敏資料或私人路徑。
- B 的課程或活動授權與 Google 原表權限要各自成立。以單一 Sheets 存取介面回報授權缺失、原表無讀寫權或外部讀寫失敗。A 的解析及回填規劃以假來源測試，真實存取留給本機人工驗收。

### 辨識、預覽與版本（D05、D10、D11、D15、D19）

1. 讀取選定分頁的儲存格與合併範圍。從相同列唯一地找出正規化表頭，依表頭的合併範圍定位各欄區。從題號欄辨識正整數及其原始顯示題號，使用實際列順序。
2. 單題定位作答欄內唯一答案格。題組只使用跨列合併題號涵蓋的列，從作答欄辨識半形、全形括號標號並找其右側答案格，答案格合併時取左上角。歧義停止預覽並指出位置。這些判斷依來源結構，可涵蓋移動欄列的講義。
3. 預覽保留題號、作答格數及提交單位數。教師確認的來源才保存版本。在同一筆資料庫交易保存講義版本、題目與填空識別，以及供 A 回填的來源對應，避免半成品被 B 選用。D19 文字交付待介面確認，文字只從題目區擷取。
4. A 以試算表 ID、分頁 ID 及已辨識結構定位來源。填空識別碼在該版本內固定，與可變的列欄座標分開保存。B 固定版本並保存有序的題目與填空；新匯入不會改寫既有版本。分頁名稱與自訂講義名稱屬 D17 的預設，列於待確認小節。

### A／B 函式與資料介面

#### 已實作的 Foundation 查詢契約

| 函式簽章 | 回傳結構與權限 | 既有錯誤 |
| --- | --- | --- |
| `list_available_catalogs(teacher_id)` | 回傳有效教師可存取的清單摘要陣列，每筆含 `import_id`、`import_version`、`title`、`question_count`。有效教師若無可用清單，回傳空陣列。 | 無效教師為 `TEACHER_REQUIRED`（401）。 |
| `get_catalog(teacher_id, import_id, import_version)` | 精確配對指定講義識別碼及版本。回傳 `import_id`、`import_version`、`questions`。 | 無效教師為 `TEACHER_REQUIRED`（401）。其他教師的清單、未知講義或未知版本統一回傳 `CATALOG_NOT_FOUND`（404），避免揭露清單是否存在。 |

- `questions` 依原始講義順序回傳。每題保留 `question_id`、原題號字串 `display_number`、`type`（`single`／`group`）與 `items`。每個 item 保留 `item_id`、`label`、`order`，依來源順序從 1 編號。單題恰有一個 item，`label` 為空字串。
- 每個已保存版本的題目與填空識別碼固定。回填對應使用該版本的 `question_id` 和 `item_id`，A 內部再定位 Sheets 格位；顯示題號、標號和順序用於呈現。清單維持既有回傳結構，作答區內容、格位與憑證留在 A。Activities 與 Quiz 透過這兩個函式存取。

#### 待確認的 B 整合介面

| 介面 | 待 A／B 確認 |
| --- | --- |
| D15 課程及歷史活動授權 | 課程歸屬的傳遞方式、課程內清單由誰篩選、建立活動時由誰驗證版本歸屬，以及歷史回填的權限檢查。兩個既有查詢簽章維持教師範圍。 |
| D19 題目文字 | 題目與小題文字使用的傳遞介面和欄位，以及如何對應同一版本的 `question_id`、`item_id`。 |
| 結算快照 `get_ended_snapshot()` | 實際接點、授權參數、版本與答案欄位、無勝組表示及結算錯誤回應。共同文件有 `RESULT_NOT_READY` 的設計約定，本地 Foundation 尚未提供該介面。 |

A 可先用測試替身驗證已結束且已結算、版本一致與同一勝組完整答案等條件。B 負責產出勝組與結算結果（D01、D02、D08），A 依快照回填。

### 回填計畫、來源檢查與恢復（D05、D07、D09、D10、D11、D14）

1. 檢查教師權限並讀取指定活動的已結算快照及固定版本。驗證題目及填空識別能完整對上，拒絕不相符的結果。將無勝組題目標記略過。題組的所有預期答案來自同一勝組。
2. 依原分頁當下的表頭、題號、小題標號與合併範圍重建對應，產生給教師確認的預覽。暫採的作法是顯示位置、目前內容與將寫入的答案，使教師能辨識既有內容會如何變更。記錄確認時的題目結構、格位、原值與預期值。
3. 寫入前再讀來源並比對已確認計畫。位置或相關內容改變且題目仍可配對時，重建預覽並等待再次確認。題目集合改變或無法建立一對一對應時要求重新匯入並核對結果，活動保留原版本。只寫入答案格的值，以原始文字送出；不更新格式、合併範圍或標號。
4. 回讀每格並與預期答案比對，按格記錄已完成、未驗證或衝突。重試使用同一活動版本與勝組結果，先重新辨識和回讀。回讀已等於預期的格位直接完成；未完成且原值仍符合已確認預覽的格位才續寫；遇到其他值或位置變動先提示衝突或要求重新確認。授權或網路中斷後沿用同一計畫檢查，避免重送時覆蓋已完成的答案。

| Notes 錯誤碼提案 | 處理 |
| --- | --- |
| `NOTES_FORMAT_INVALID` | 顯示缺少或重複的表頭、題號或小題定位歧義，供教師修正。 |
| `SHEETS_AUTH_REQUIRED`、`SHEETS_ACCESS_DENIED` | 分別提示執行授權指令或檢查分頁所在試算表的存取權。 |
| `SOURCE_PREVIEW_STALE`、`SOURCE_REIMPORT_REQUIRED` | 分別要求確認新版預覽或重新匯入，保留既有活動版本。 |
| `SHEETS_READ_FAILED`、`SHEETS_WRITE_UNVERIFIED`、`WRITEBACK_CONFLICT` | 提供可重試的提示，必要時標示受影響的題目與填空。結果未知時先回讀再決定是否續寫。 |

## Risks / Trade-offs

- **來源在確認後又被編輯**　每次寫入前重檢來源，縮小檢查與寫入的時間差，寫後逐格回讀。外部編輯可能發生在兩次請求之間，回讀衝突需呈現給教師處理。
- **OAuth 過期、網路中斷或寫入完成但回應遺失**　標示未驗證的項目，使用同一快照恢復，先定位與回讀才決定是否續寫。
- **A／B 開發時間不同**　先以單題、兩格題組、無勝組及未結算資料做契約驗證。以真實 B 模組及不同版面講義進行人工驗收。

## Migration Plan

Foundation 已建立 `teachers` 表。本 Change 的實作階段會透過既有 `init-db` 新增 Notes 資料表。初始化應支援空白 SQLite 和已有教師帳號的 SQLite，且可重複執行。若要撤下本功能，先停用 Notes 的匯入和回填入口並保留版本與回填紀錄；來源 Sheets 已寫入的內容由教師依原表紀錄確認。

## Open Questions

- **待確認，D17**　沿用來源分頁名稱或自訂名稱、顯示來源資訊、多分頁逐一預覽和保存。以此安排預設介面，兩組確認後再定字串與多分頁操作細節。
- **待 A／B 核對**　D15 課程授權及篩選、D19 文字傳遞與歷史活動結算快照，詳見待確認的 B 整合介面。
