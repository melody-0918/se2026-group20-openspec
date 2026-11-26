# Spec Delta

## MODIFIED Requirements

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
