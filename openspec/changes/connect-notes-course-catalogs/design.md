# Design

## Context

依 proposal 與 [activities delta spec](specs/activities/spec.md) 的範圍完成模組接線。Notes 已提供教師範圍清單介面及課程範圍 `list_course_catalogs(teacher_id, course_id)`，並透過 `NOTES_COURSE_ACCESS` 驗證課程；目前應用程式尚未提供該 callback。Activities 已有自己的 `list_course_catalogs`，回傳 activities `course_catalogs` 關聯，且建立活動時以該關聯限制所選版本。

## Goals / Non-Goals

**Goals:**

- 讓 Notes 所有課程範圍請求以 activities 的教師課程所有權作為授權來源。
- 讓正式講義在課程頁按課程隔離，且只有經驗證的同課程版本可加入活動課程清單。
- 讓教師能在活動課程與 Notes 講義頁之間往返，並讓瀏覽器錯誤回到可存取的頁面。

**Non-Goals:**

- 不改 notes 的清單查詢函式、匯入、版面辨識、回填邏輯或資料表。
- 不交付題目敘述／小題文字，不接入結算快照或 quiz；D13（含準備中）、D18、D19、D22 不在此 change 範圍。
- 不移除示範清單，不做 CSV 匯出。

## Decisions

### 由 Activities 提供 Notes 課程授權 callback（D04、D15）

- 在 activities 提供可由 app factory 註冊的課程授權函式。輸入 `teacher_id` 與字串 `course_id`，只查詢 `courses` 是否有兩者相符的資料並回傳布林值；無效或不存在的配對回傳 `False`，不丟出資源存在性差異錯誤。
- `create_app` 在套用 `test_config` 後，僅在 `NOTES_COURSE_ACCESS` 未設定時註冊預設函式。這保留測試或部署設定提供的 callback 覆寫。Notes 既有教師有效性檢查仍先執行；課程 callback 回傳 `False` 時由 Notes 統一回 `COURSE_FORBIDDEN`（403）。
- 此函式只負責課程擁有權查詢，不呼叫 Notes、不新增表格、不讀取 notes 資料表。Notes 目前不反向匯入 activities，故可避免循環相依。
- 替代方案：在 Notes 中重複管理課程／授權資料。未採用，因 activities 已是教師課程擁有權的權威來源，重複資料會產生不一致。

### 課程頁清單來源按示範模式分流（D11、D15）

- 從 Notes 的課程範圍 `list_course_catalogs` 匯入時使用別名（例如 `list_notes_course_catalogs`），保留 activities 現有同名函式供其 course_catalogs 關聯使用。
- 非示範模式：課程頁可用清單與加入驗證皆以該 Notes 課程範圍函式回傳的精確 `import_id`、`import_version` 為準。版本不在該課程時不寫入 activities 關聯並回穩定的 `CATALOG_NOT_FOUND`。
- 示範模式：延續 `list_available_catalogs(teacher_id)`、`get_catalog` 與目前加入流程，確保沒有 Google 憑證時仍可展示與測試。
- 成功加入後仍保存 activities 自己的 `course_catalogs` 關聯；`create_activity` 維持以此關聯限制版本，再用既有 `get_catalog(teacher_id, import_id, import_version)` 固定題目識別。這保持 change ② 行為及快照流程，不需要資料表遷移。
- 替代方案：移除 activities `course_catalogs`，直接讓 activities 每次都查 Notes。未採用，因為這會擴大為資料模型變更，且打破既有「課程已加入清單才可建活動」契約。

### 課程頁與 Notes 頁導覽（D15）

- 活動課程頁以 `url_for` 指向 `notes.workspace`，帶入同一 `course_id`，按鈕文字固定為「匯入／管理講義」。
- Notes 頁新增連到 `activities.teacher_course` 的「回課程頁」連結。`notes.html` 屬 A 負責維護的模板，實作前須告知 A 並協調修改；本 change 不改該頁現有匯入或回填操作。
- 所有 URL 使用 Flask endpoint 產生，不自行拼接路徑。

### Notes 瀏覽器錯誤頁與返回目的地（D04、D15）

- 擴充共用 `AppError` handler：`/api/` 路徑維持 JSON；Notes Blueprint 的瀏覽器頁面錯誤使用既有 `error.html`，保留 `AppError.status_code`、中文訊息及錯誤代碼。Activities 既有 HTML 錯誤行為不變。
- `COURSE_FORBIDDEN` 一律返回 `/activities/teacher/courses`，避免把無權檢視的課程頁當成可返回目的地。其他 Notes 頁面錯誤若有 `course_id` 且授權 callback 確認教師擁有課程，返回該課程 Notes workspace；沒有可授權課程時返回教師課程列表。
- Notes `notes.html` 以既有 `error` 或 `writeback_review` 顯示的結果是正常頁面回應，不經 `AppError` handler；本 change 不改其呈現。此 change 不宣稱 `/api/` 外非瀏覽器 JSON 請求的新錯誤行為，現有 `/api/` 合約維持不變。
- 替代方案：所有錯誤都回固定教師首頁。未採用，因為已授權課程內的來源／憑證錯誤需要讓教師能回到原工作脈絡，而 COURSE_FORBIDDEN 必須避免返回無權課程。

### Notes 解析、回填及敏感設定邊界

- 本 change 不改 Notes 格式解析。既有實作會在同一表頭列辨識「題號」「題目」「作答」，以題號正整數與合併範圍界定題目，再依題組標號或涵蓋整題的唯一答案格辨識小題及作答格。回填沿用已保存版本的題目／小題識別重新定位來源，只寫目標答案格，確認來源與原值後保留小題標號及儲存格格式。這些責任仍由 Notes 實作與其 change 規格負責；本 change 不改變解析、回填輸入輸出契約，也不新增其資料表。
- OAuth client 與 token 檔案仍放在 repo 外，由 `NOTES_GOOGLE_CLIENT_SECRETS` 與 `NOTES_GOOGLE_TOKEN` 指向；一般 HTTP 請求不啟動 OAuth。教師密碼沿用既有雜湊儲存，secret key 沿用環境設定。本 change 不加入或複製任何憑證。

## Risks / Trade-offs

- **Notes 的課程 callback 未註冊或被錯誤覆寫時，授權可能失敗。** → app factory 提供預設值、測試明確覆寫並分別測試擁有者與非擁有者；Notes 仍將無權限統一映射為 `COURSE_FORBIDDEN`。
- **正式清單範圍查詢和示範清單查詢形狀略有不同。** → 兩者皆回傳相同摘要欄位，讓模板只依摘要呈現；在測試中分別覆蓋正式與示範分支。
- **共用錯誤 handler 調整可能影響其他 Blueprint。** → 僅對 Notes 頁面與既有 Activities 頁面做 HTML 分流，API 保留 JSON，並測試權限錯誤、一般 Notes AppError 與 API 錯誤。
- **Notes 頁模板由 A 維護。** → 實作其返回課程連結前先告知 A；匯入與回填程式邏輯不在修改範圍。

## Migration Plan

不需資料庫遷移。部署應用程式後，`create_app` 即提供課程 callback；既有課程清單關聯及 notes 已保存版本保留。若需回退，可還原本 change 的 app factory、activities 頁面、模板與錯誤 handler 變更；不需刪除資料表或 notes 資料。
