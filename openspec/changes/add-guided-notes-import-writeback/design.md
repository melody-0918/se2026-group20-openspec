# Design

## Context

Foundation 已合併，提供 Flask app factory、教師登入、CSRF、SQLite 及 `/notes`。A 已有正式講義儲存、課程清單與固定版本文字查詢、OAuth 和回填驗證。B 的課程授權、活動顯示與結算快照仍待接入。參照 [Foundation 主規格](../../specs/app-foundation/spec.md)、[提案](proposal.md)、[差異規格](specs/guided-notes/spec.md)。

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

1. 讀取選定分頁的儲存格與合併範圍。從相同列唯一地找出表頭，依表頭的合併範圍定位各欄區。題號以原始正整數或純數字字串判斷，識別碼使用正規化後的題號並依實際列序排列。保留顯示題號 `01`，忽略原始數值為 `1.4` 但格式顯示為 `1` 的格位。
2. 單題使用作答欄內唯一覆蓋整題的答案格，可跨欄或跨列。題組只使用題號合併涵蓋的列，辨識至少兩個不重複的小題。標號接受半形、全形括號和括號內空白，保留來源文字，從標號右界找同列唯一答案格。合併答案格寫入左上角。跨題、跨小題或有多個可能答案格時，停止預覽並指出位置。
3. 預覽保留題號、作答格數及提交單位數。教師確認後，在同一筆資料庫交易保存版本、題目與填空識別及 A 的來源對應。D19 文字只取題目欄區內的儲存格錨點，依列與欄順序拼接非空文字。題組的完整文字含小題文字，每個小題另外取得本列到下一小題前的題目欄文字；合併文字按錨點所在列歸屬。A 僅交付文字，學生頁由 B 決定顯示方式及填答時機。
4. A 以試算表 ID、分頁 ID 及已辨識結構定位來源。填空識別碼在該版本內固定，與可變的列欄座標分開保存。B 固定版本並保存有序的題目與填空；新匯入不會改寫既有版本。分頁名稱與自訂講義名稱屬 D17 的預設，列於待確認小節。

### A／B 函式與資料介面

#### 已實作的 Foundation 查詢契約

| 函式簽章 | 回傳結構與權限 | 既有錯誤 |
| --- | --- | --- |
| `list_available_catalogs(teacher_id)` | 回傳有效教師可存取的清單摘要陣列，每筆含 `import_id`、`import_version`、`title`、`question_count`。有效教師若無可用清單，回傳空陣列。 | 無效教師為 `TEACHER_REQUIRED`（401）。 |
| `get_catalog(teacher_id, import_id, import_version)` | 精確配對指定講義識別碼及版本。回傳 `import_id`、`import_version`、`questions`。 | 無效教師為 `TEACHER_REQUIRED`（401）。其他教師的清單、未知講義或未知版本統一回傳 `CATALOG_NOT_FOUND`（404），避免揭露清單是否存在。 |

- `questions` 依原始講義順序回傳。每題保留 `question_id`、原題號字串 `display_number`、`type`（`single`／`group`）與 `items`。每個 item 保留 `item_id`、`label`、`order`，依來源順序從 1 編號。單題恰有一個 item，`label` 為空字串。
- 每個已保存版本的題目與填空識別碼固定。回填對應使用該版本的 `question_id` 和 `item_id`，A 內部再定位 Sheets 格位。兩個教師範圍查詢維持既有回傳結構。作答區內容、格位與憑證留在 A。

#### A 提供的課程查詢與文字資料（D15、D19）

| 函式簽章 | 回傳結構與權限 |
| --- | --- |
| `list_course_catalogs(teacher_id, course_id)` | 回傳同樣的摘要欄位，只列出該教師在已授權課程內保存的正式版本。 |
| `get_course_catalog(teacher_id, course_id, import_id, import_version)` | 依教師、課程、講義及精確版本配對。明細沿用 Foundation 的識別與順序欄位，每題另有 `question_text`，題組每個 item 另有 `item_text`。兩個文字欄位皆為字串；單題的作答 item 沿用原形狀。作答欄內容、座標及來源資料不交付。 |

兩個課程查詢、課程內預覽、保存與回填共用 `NOTES_COURSE_ACCESS(teacher_id, course_id) -> bool`。`course_id` 是 B 課程識別碼的字串。無效教師為 `TEACHER_REQUIRED`（401），未接入授權為 `NOTES_INTEGRATION_PENDING`（503），課程無權限為 `COURSE_FORBIDDEN`（403）。已通過課程授權後，與該教師及該課程無關的版本和未知版本統一為 `CATALOG_NOT_FOUND`（404）。課程查詢沒有示範資料 fallback。

B 接入時由 Activities 註冊實際課程授權，在活動建立時呼叫 `get_course_catalog()` 驗證並固定所選版本的題目與 items。學生端沿用同一版本的識別碼配對 `question_text`、`item_text` 和作答欄。開場前唯讀、開場後才可提交，題組仍整組送出。以上簽章、DTO 欄位和 Flask 設定名稱為 OpenSpec 內部介面，正式呼叫鏈與學生端驗收仍待 B。

#### B 待接入的已結算快照（D01、D02、D06、D08、D10、D11、D14）

共同需求定義 `get_ended_snapshot()` 只在活動已結束且已結算時交付不可變結果。B 負責活動及歷史資料授權、使用活動固定的課程與版本，以及選出每題唯一勝組。同組主動重送成功才取代舊答案並取得新受理順序，同一請求的網路重試維持原受理結果，結束前成功受理的有效答案依伺服器受理順序排名，第一名為勝組。A 不重新排名。

B 在完成 `get_ended_snapshot()` 後註冊 A 的 `NOTES_ENDED_SNAPSHOT(teacher_id, activity_id)` 接點，依實際活動及歷史權限轉接為 `notes_writeback.EndedSnapshot`。活動不存在或教師無權限時轉為 `None`，A 統一回報 `ACTIVITY_NOT_FOUND`（404）。活動尚未結束或結算時轉為 `AppError` 的 `RESULT_NOT_READY`（409）。A 本身也拒絕未關閉或未結算的快照；缺少接點回報 `NOTES_INTEGRATION_PENDING`（503）。正式 adapter 及 B 錯誤轉譯仍待整合。

| A 的 DTO | 欄位與限制 |
| --- | --- |
| `EndedSnapshot` | `activity_id: str`、`teacher_id: int`、`import_id: str`、`import_version: str`、`closed: bool`、`settled: bool`、`questions: tuple[QuestionResult, ...]`。兩個布林值均為真。`import_id` 與 `import_version` 必須是活動建立時固定者，A 會以該教師及回填所選課程檢查版本歸屬。 |
| `QuestionResult` | 每個固定版本 `question_id` 恰有一筆。`winner_id` 為勝組的非空字串識別碼，`answers: tuple[Answer, ...]` 為該組全部填空答案。無勝組時 `winner_id=None` 且 `answers=()`。 |
| `Answer` | `item_id: str`、`text: str`。有勝組時所有預期 item 都須出現一次；A 以識別碼對照，不以快照陣列位置配對。 |

上述 DTO 和 `process_writeback(sheets_factory, snapshot, course_id, preview_id=None)` 已用人工輸入和測試替身驗證。跨課程、未知版本、未知或重複題目、缺少／重複／未知填空等不相符的快照回 `RESULT_CATALOG_MISMATCH`（409）。

### 回填計畫、來源檢查與恢復（D05、D07、D09、D10、D11、D14）

1. 檢查教師權限並讀取指定活動的已結算快照及固定版本。驗證題目及填空識別能完整對上，拒絕不相符的結果。將無勝組題目標記略過。題組的所有預期答案來自同一勝組。
2. 依原分頁當下的表頭、題號、小題標號與合併範圍重建對應，產生給教師確認的預覽。暫採的作法是顯示位置、目前內容與將寫入的答案，使教師能辨識既有內容會如何變更。記錄確認時的題目結構、格位、原值與預期值。
3. 寫入前再讀來源並比對已確認計畫。位置、題目結構或確認前的目標原值及其顯示文字改變且題目仍可配對時，重建預覽並等待再次確認。題目集合改變或無法建立一對一對應時要求重新匯入並核對結果，活動保留原版本。只寫入答案格的值，以原始文字送出；不更新格式、合併範圍或標號。
4. 回讀每格並與預期答案比對，按格記錄已完成、未驗證或衝突。重試使用同一活動版本與勝組結果，先重新辨識和回讀。回讀已等於預期的格位直接完成；未完成且原值仍符合已確認預覽的格位才續寫；遇到其他值或位置變動先提示衝突或要求重新確認。授權或網路中斷後沿用同一計畫檢查，避免重送時覆蓋已完成的答案。

回填 HTTP JSON 遇到下列狀態時回傳共用 `error.code`、`error.message`，同時保留 `writeback_review` 的狀態、格位結果及可能的回讀原因 `issue`。如單獨提交已失效的預覽識別碼，共用錯誤仍為 `SOURCE_PREVIEW_STALE`。

| `writeback_review.status` | `error.code`、HTTP 狀態與處理 |
| --- | --- |
| `source_changed` | `SOURCE_PREVIEW_STALE`（409）。使用回應中的新 `preview_id` 核對並重新確認。 |
| `conflict` | `WRITEBACK_CONFLICT`（409）。核對有衝突的格位，避免覆蓋。 |
| `unverified` | `SHEETS_WRITE_UNVERIFIED`（502）。保留原快照，重試時先回讀再決定是否續寫。 |

格式無法唯一辨識時回 `NOTES_FORMAT_INVALID`；回填時若來源已無法和固定版本一一配對，則回 `SOURCE_REIMPORT_REQUIRED`。`SHEETS_AUTH_REQUIRED`、`SHEETS_ACCESS_DENIED` 及 `SHEETS_READ_FAILED` 分別指示授權、原表權限或讀取問題。

## Risks / Trade-offs

- **來源在確認後又被編輯**　每次寫入前重檢來源，縮小檢查與寫入的時間差，寫後逐格回讀。外部編輯可能發生在兩次請求之間，回讀衝突需呈現給教師處理。
- **OAuth 過期、網路中斷或寫入完成但回應遺失**　標示未驗證的項目，使用同一快照恢復，先定位與回讀才決定是否續寫。
- **A／B 開發時間不同**　先以單題、兩格題組、無勝組及未結算資料做契約驗證。以真實 B 模組及不同版面講義進行人工驗收。

## Migration Plan

Notes 資料表沿用 `init-db` 初始化，可在空白 SQLite 或已有教師的 SQLite 重複執行。已保存版本的文字取自既有 `layout` 的 `source_text` 欄位，舊版維持原來捕捉的文字，無須修改資料表。部署後如果既有回填預覽保存的結構缺少新的答案列範圍，首次操作會要求重新預覽。若舊版本曾將非整數誤存為題號，重讀來源後集合不符會回 `SOURCE_REIMPORT_REQUIRED`，活動原綁定的版本保留。來源 Sheets 的已寫入內容由教師依原表紀錄確認。

## Open Questions

- **待確認，D17**　沿用來源分頁名稱或自訂名稱、顯示來源資訊、多分頁逐一預覽和保存。以此安排預設介面，兩組確認後再定字串與多分頁操作細節。
- **待 B 接入及驗收**　課程授權、建立活動時的課程版本驗證、唯讀題目與小題呈現、歷史活動授權，以及已結算快照和錯誤轉接。
