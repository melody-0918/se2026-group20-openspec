# Design

## Context

參照 [proposal.md](proposal.md) 說明變更動機及範圍。現有活動資料已固定 `import_id`、`import_version` 及有序 `activity_questions`；`activities.immediate_transaction` 使用 SQLite `BEGIN IMMEDIATE`，`assert_submission_eligible` 檢查課堂、活動、組別與題目。Notes 提供教師範圍 `get_catalog`、課程範圍 `get_course_catalog`，回填端使用 `EndedSnapshot`、`QuestionResult`、`Answer` DTO。現有教師狀態 API 以 `state_version` 判斷是否整頁重新載入；學生頁每秒輪詢。

## Goals / Non-Goals

**Goals:**

- 在活動結束與提交競爭時，以同一 SQLite 寫入序列決定受理先後，並穩定保存有效答案與順位。
- 讓教師、學生、CSV 匯出及 Notes 回填從同一組提交資料取得各自授權範圍內的結果。
- 保留既有活動題目資料表，讓活動固定版本成為小題結構唯一來源。

**Non-Goals:**

- 不更動 Notes 的匯入、辨識、版本儲存及回填實作或資料表；不在 quiz 複製題目、小題或顯示文字資料。
- 不改 activities schema 或加入新的順位策略；不對答案作正誤評分。

## Decisions

### 提交記錄與序位

quiz 新增自己的提交與答案資料表，不改 `activities` 或 `activity_questions`。提交記錄包含活動、組別、主題號、用戶端送出識別碼、受理序號及目前有效標記；答案列以 `item_id` 保存文字。每個成功的主動提交新增一筆提交記錄，並在同一交易將該組該活動該題的前一筆標為非有效。舊記錄保留以支援請求重播與稽核，順位只從有效記錄計算。

`accepted_sequence` 使用資料庫交易內配置的單調遞增整數，不以時間戳排序。以 `ROW_NUMBER()`（或等價穩定排序）依序號計算每題有效提交順位；最低序號為勝組。兩組相同時間送出時，`BEGIN IMMEDIATE` 將寫入序列化，只有先取得交易並完成受理者序號較小。

### 提交交易、資格與重播

提交流程使用 `activities.immediate_transaction(connection)` 開始交易，第一個資格動作呼叫 `assert_submission_eligible(connection, classroom_id, activity_id, team_id, question_id)`，並只在同一連線寫入。先在交易外驗證請求形狀、答案非空與每個 item 不超過 200 字；item 集合須與活動固定版本完全相符，否則拒絕整筆。

識別碼唯一範圍為 `(team_id, activity_id, question_id, submission_id)`。資格檢查成功後若已有同範圍識別碼，回傳原受理序號與結果，不新增記錄。若活動已結束或課堂已關閉，仍先呼叫資格檢查；檢查拒絕後，只查詢上述完整複合範圍的既有識別碼，有紀錄才重播原受理結果，沒有則回傳資格錯誤。重播不會寫資料，也不會用識別碼查詢或回傳他組資料。相同範圍識別碼若重帶不同答案，回 `SUBMISSION_ID_REUSED`（409），不洩漏其他組狀態。

送出失敗不標記舊提交失效。建議錯誤碼：無效請求 `SUBMISSION_INVALID`（400）、空白答案 `ANSWER_REQUIRED`（400）、小題超長 `ANSWER_TOO_LONG`（400）、重用識別碼但內容不一致 `SUBMISSION_ID_REUSED`（409）；沿用 activities 的 `ACTIVITY_NOT_ACTIVE`、`CLASSROOM_CLOSED`、`ACTIVITY_CLASSROOM_MISMATCH`、`TEAM_CLASSROOM_MISMATCH`、`QUESTION_NOT_IN_ACTIVITY` 等拒絕。回應統一使用 `error.code`、`error.message`。

### 固定版本及身分解析

quiz 先從活動、課堂及課程關聯讀取活動擁有者 `teacher_id`，再使用活動的 `import_id`、`import_version` 呼叫 `notes.get_catalog(teacher_id, import_id, import_version)`。任何用戶端傳入的 `teacher_id` 不作為授權依據；教師路由仍須驗證登入者擁有該活動，學生路由使用有效 proof 對應的課堂與組別。

`get_catalog` 的 `questions` 和 `items` 提供 `question_id`、`display_number`、`item_id`、`label`、`order`。提交和結果以識別碼關聯，不依陣列位置猜測；完整 item 集合須符合固定版本。正式與示範資料均走 Notes 公開 API。Catalog 權限／版本錯誤沿用 Notes 的 `TEACHER_REQUIRED`、`CATALOG_NOT_FOUND`，quiz 不直接讀 Notes 資料表；提交、順位及回填識別不依賴題目文字欄位。

### D19 固定版本文字呈現

正式模式依活動、課堂及課程關聯由伺服器解析 `teacher_id` 與 `course_id`，使用活動固定的 `import_id`、`import_version` 呼叫 `get_course_catalog(teacher_id, course_id, import_id, import_version)`。學生端只接收該介面提供的 `question_text`、`item_text` 及必要題目／小題識別、題號與標號；不序列化來源答案格內容、試算表／分頁識別或其他來源資訊。不得信任用戶端傳入的教師或課程識別，也不修改 `notes.py` 或 Notes 資料表。

示範模式改用 `get_catalog(teacher_id, import_id, import_version)`；示範 catalog 沒有文字時，只顯示題號與小題標號，不嘗試從來源補取或自行生成文字。活動建立／切換到新活動時取得一次固定題目內容，後續每秒輪詢只讀取階段、提交狀態與必要結果，不重送題目文字。準備中顯示唯讀題目與小題文字且不建輸入框；搶答中顯示相同文字及作答欄；已結束仍保留文字並顯示允許的結果。D18 的開始前唯讀看題要求由 D19 一併涵蓋。

### 查詢介面與結果結構

quiz 提供 `get_activity_results(teacher_id, activity_id)` 給 A 的 CSV 匯出程式。成功時只回傳已結束活動；不具活動權限回 `ACTIVITY_NOT_FOUND`（404），未結束回 `RESULT_NOT_READY`（409）。回傳 JSON 形狀如下：

```json
{
  "activity_id": "...",
  "import_id": "...",
  "import_version": "...",
  "questions": [
    {
      "question_id": "...",
      "display_number": "01",
      "winner_id": "team-id-or-null",
      "winner_name": "team-name-or-null",
      "teams": [
        {
          "team_id": "...",
          "team_name": "...",
          "answers": [{"item_id": "...", "text": "..."}],
          "accepted_sequence": 12,
          "rank": 1,
          "is_winner": true
        }
      ]
    }
  ]
}
```

無勝組題目的 `winner_id`／`winner_name` 為 `null`，`teams` 為空陣列。每個組別答案依固定 `item_id` 對應；勝組是 `rank == 1` 的組別。欄位命名與題號／小題識別對齊，實際 CSV 欄位由 A 依此查詢結果確認。

`get_ended_snapshot(teacher_id, activity_id)` 依教師活動權限及活動狀態建立 DTO：

- 活動存在、教師有權但尚未結束：回傳 `EndedSnapshot(..., closed=False, settled=False, ...)`；Notes 顯示 `RESULT_NOT_READY`（409）。
- 活動不存在或教師無權：回傳 `None`；Notes 顯示 `ACTIVITY_NOT_FOUND`（404）。
- 活動已結束且已結算：使用固定 catalog 對答案排序，回傳 `EndedSnapshot(..., closed=True, settled=True, ...)`。

每一固定 `question_id` 恰一筆 `QuestionResult`；`winner_id` 使用勝組 `team_id` 字串，勝組答案以固定 item 順序轉成完整 `Answer(item_id, text)` tuple。無勝組回 `QuestionResult(question_id, None, ())`。

`create_app` 設定 `app.config["NOTES_ENDED_SNAPSHOT"]` 為此 adapter，使 Notes 現有回填入口可使用；不更改 Notes DTO 或回填程式。活動終態與提交資格共用即時交易，活動結束後不再新增提交，因此有效提交集、順位與快照保持穩定。

### 師生查詢與同步

維持活動階段資料由 activities 管理，新增 quiz 狀態 API 分別供已登入教師及 proof 學生讀取，避免把答案寫入活動狀態或把 `state_version` 改成每次提交遞增。教師課堂頁每秒查詢 quiz 狀態端點，將答案／順位區塊局部更新；此方式可在新受理後約 2 秒內反映，亦避免每筆答案觸發整頁重載。學生端只從自己的 quiz 狀態端點取得送出狀態；只有階段變更可更新活動資訊，輸入欄位值由瀏覽器保留，不以重新渲染表單的方式刷新。

搶答中教師端收到全組提交與排名；學生端只收到自己的已送出答案及是否提交，不含排名或其他組識別。活動結束且課堂開放時，教師取得全部結果；學生只收到每題勝組名稱／答案及自己組答案／順位。課堂一旦關閉，學生狀態頁在 quiz 結果查詢前短路，只回報課堂已結束，不附活動結果。

### 結束活動的教師入口

在活動狀態為 ended 時，教師課堂頁顯示活動 ID，並產生帶該課程 ID 的 Notes 課程入口。只呈現入口，不自動觸發回填；Notes 仍執行自己的權限及已結算快照檢查。

### DB 初始化與部署

新增 quiz 表由既有 `init-db` schema 初始化；初始化需可在空資料庫與已有 activities／notes 資料庫重複執行。既有活動不含提交，因此部署後舊活動的結算結果為所有題目無勝組；不得以新版本 catalog 重建或改寫活動題目識別。

## Risks / Trade-offs

- **每秒回傳所有答案會隨組數增加負載** → 只查單一活動且只回傳已受理的必要欄位；以現有本機課堂規模作驗收，避免額外長輪詢框架。
- **保留歷史提交增加資料量** → 每筆只保存文字與識別，不複製題目描述；目前沒有刪除答案功能，資料量隨成功重送次數線性增加。
- **活動結束與提交順序錯誤會改變勝組** → 兩者必須共用同一 SQLite 連線交易模型，並驗證只有結束交易前受理的提交進結果。
- **固定 catalog 版本若不可讀會妨礙答案 item 對應** → Notes 版本為不可變版本；明細查詢失敗時拒絕結果快照並回傳明確錯誤，不以最新版本代替。
- **學生 API 錯誤實作可能洩漏進度** → 以 proof 取得 team_id，服務端篩選查詢結果；送出識別碼不作授權憑證，並驗證每種階段回應欄位。
- **D19 顯示資料若混入來源資訊或答案格會洩漏內容** → 正式學生 DTO 使用 `get_course_catalog` 的文字白名單及必要識別欄位組裝，不傳遞 Notes 內部來源欄位；示範模式只採 `get_catalog` 回傳。

## Change ② 測試預期

activities MODIFIED 需求改變 change ②（`add-classroom-activity-phases`）的兩項既有行為預期：關課後學生狀態，以及學生狀態不含題目敘述。apply 時允許只更新這兩項對應的既有測試預期；change ② 的其餘測試預期不得修改。

## Migration Plan

1. 在 schema 初始化中加入 quiz submission 與 answer 表，確認重複初始化不變更既有活動資料。
2. 部署 quiz 提交／查詢功能及 `NOTES_ENDED_SNAPSHOT` 註冊；舊活動不存在提交資料，結果按無勝組呈現。
3. 若需回退，移除路由註冊即可停止新功能；保留 quiz 表及歷史資料，避免丟失已受理紀錄。不得回退活動狀態或重開已結束活動。

## Open Questions

- CSV 匯出最終欄名與欄位展開方式需與 A 確認；本 change 先固定 `get_activity_results` 結構及識別欄位。
