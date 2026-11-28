# quiz Specification

## Purpose

提供課堂搶答的組別作答提交、受理順位、活動結算與依身分限制的結果查詢，並交付 CSV 匯出及 Guided Notes 回填所需的結果資料。

## Requirements

### Requirement: 搶答期間依題號受理整組答案
quiz SHALL 僅受理搶答中活動所屬組別對該活動題目的提交；每個題號為一個提交單位，題組全部小題須一併送出。（D02、D03、D10、D11、D13）

#### Scenario: 單題與完整題組提交
- **WHEN** 組別在搶答中提交活動固定題目的非空答案，且題組每個小題均有答案
- **THEN** 系統受理該主題號的一筆提交，並保存每個 `item_id` 對應的答案

#### Scenario: 空白、部分題組或超長答案
- **WHEN** 任一小題答案空白或只有空白字元、題組缺少小題答案，或任一小題答案超過 200 字
- **THEN** 系統以中文錯誤拒絕整筆提交，且該組原有有效答案與順位維持不變

#### Scenario: 不合資格提交
- **WHEN** 提交來自準備中、已結束或關閉課堂，或組別／題目不屬於指定活動與課堂
- **THEN** 系統拒絕提交，且不新增或取代有效答案

### Requirement: 重送受理結果具冪等性且成功主動重送重新排名
quiz SHALL 以送出識別碼辨識同一次請求；只有同一組、同一活動、同一主題號及相同識別碼才重播原受理結果，且不得藉此取得他組資料。不同識別碼的成功提交取代同組該題有效答案並取得新順位。（D01、D02、本組自行決定）

#### Scenario: 同一送出重試
- **WHEN** 同一組對同一活動及主題號以相同送出識別碼重試已受理的提交
- **THEN** 系統回覆原受理結果與原順位，不建立新順位，且不回傳其他組資料

#### Scenario: 成功主動重送相同或不同內容
- **WHEN** 組別以新送出識別碼重送同一活動及題號，且新答案符合受理條件
- **THEN** 新答案取代舊答案並依新受理序號重新排名，即使答案內容相同亦然

#### Scenario: 主動重送被拒
- **WHEN** 組別重送同一題但新答案不符合受理條件
- **THEN** 系統拒絕新提交，原有效答案與順位保留

### Requirement: 受理順序決定順位與勝組
系統 SHALL 以交易內產生的唯一遞增受理序號為有效提交排序依據；每題順位第一的組別為勝組，不判斷答案正確性。（D02、D08、D10）

#### Scenario: 競爭提交排序
- **WHEN** 多組幾乎同時提交同一題
- **THEN** 每筆成功提交取得唯一穩定受理序號，較早受理者順位較前且成為勝組

#### Scenario: 同組重送後順位改變
- **WHEN** 甲組先提交、乙組後提交，之後甲組以新識別碼成功重送
- **THEN** 甲組取得較新的受理序號並排在乙組之後，乙組成為勝組

### Requirement: 結束時固定結算結果並提供回填快照
系統 SHALL 僅在活動已結束後提供不可變結算結果；快照旗標必須反映活動是否結束及是否結算。每題須有一筆結果，無人作答時勝組為空且答案為空。（D02、D06、D07、D08、D10、D11）

#### Scenario: 活動結束後結算
- **WHEN** 活動結束且教師查詢該活動結果或回填快照
- **THEN** 系統依每題有效提交順位產生固定結果，之後不因其他查詢而改變

#### Scenario: 活動未結束
- **WHEN** 查詢準備中或搶答中的活動快照
- **THEN** 活動存在且教師有權時回傳 `closed=False`、`settled=False` 的 `EndedSnapshot`，Notes 顯示 `RESULT_NOT_READY`

#### Scenario: 無人作答
- **WHEN** 活動結束時某題沒有任何有效提交
- **THEN** 該題顯示無勝組，快照包含 `winner_id=None` 且 `answers=()`

#### Scenario: 活動結束與送出同時發生
- **WHEN** 提交與結束活動或關閉課堂競爭
- **THEN** 僅在交易序列中先於結束成功受理的提交計入結算

### Requirement: 結果查詢依角色與課堂狀態隔離
quiz SHALL 依教師或學生授權及活動階段限制結果欄位；搶答結束前學生不得取得其他組作答資訊。（D04、D06、D09、D22（取代 D16）、本組決定）

#### Scenario: 搶答中教師查看即時答案
- **WHEN** 教師查看所屬課堂的搶答中活動
- **THEN** 教師可查看各組已受理答案內容及目前順位

#### Scenario: 搶答中學生查看狀態
- **WHEN** 學生組別查詢搶答中活動
- **THEN** 學生只可查看自己組每題是否已送出及已送出的內容，不可查看順位或其他組資訊

#### Scenario: 活動結束後教師查看結果
- **WHEN** 教師查詢自己有權管理且已結束的活動
- **THEN** 回傳每題所有組別的答案、順位與勝組

#### Scenario: 活動結束後學生查看結果
- **WHEN** 有效學生證明所屬課堂仍開放，且活動已結束
- **THEN** 學生看到每題勝組名稱與答案，以及自己組答案與順位，不看到其他非勝組答案

#### Scenario: 課堂關閉後學生查詢
- **WHEN** 有效學生證明所屬課堂已關閉
- **THEN** 頁面只顯示「課堂已結束」，不顯示活動結果

### Requirement: 活動題目結構依固定講義版本取得
quiz SHALL 依活動固定的 `import_id` 與 `import_version` 取得題目及小題識別與顯示文字；查詢使用的教師與課程身分必須由伺服器依活動所屬課堂解析。（D04、D11、D19）

#### Scenario: 正式及示範版本題組
- **WHEN** quiz 為活動讀取正式或示範固定版本
- **THEN** 依 `question_id`、`item_id`、`label`、`order` 對應答案，且題組 items 順序與該版本一致

#### Scenario: 用戶端提供教師識別
- **WHEN** 學生或教師提交用戶端提供的 `teacher_id` 作為題目查詢授權
- **THEN** 系統忽略該值並使用伺服器解析的活動擁有者身分，或拒絕不匹配的請求

#### Scenario: 正式版本顯示題目與小題文字
- **WHEN** 學生查看正式模式的固定版本活動
- **THEN** 系統使用伺服器解析的教師與課程識別取得 `get_course_catalog` 文字，準備中唯讀顯示題目和小題文字，搶答中顯示作答欄，已結束顯示文字與結果

#### Scenario: 示範版本及學生資料限制
- **WHEN** 學生查看示範模式活動或取得任一模式的活動內容
- **THEN** 示範模式僅顯示 `get_catalog` 提供的題號與小題標號；學生資料不含來源答案格內容或來源資訊，正式文字只取自 `get_course_catalog`

#### Scenario: 活動文字只於活動切換時取得
- **WHEN** 學生活動頁輪詢同一活動的最新狀態
- **THEN** 系統只更新狀態，不重複傳送固定版本題目及小題文字

### Requirement: 提供 CSV 結果查詢介面
quiz SHALL 提供經教師活動權限驗證的結果查詢，包含 CSV 匯出所需的每題、每組、答案、受理序號、順位與勝組資料。（D06、D08；CSV 匯出由 A 負責）

#### Scenario: 有權教師取得 CSV 資料
- **WHEN** 有權教師呼叫 `get_activity_results(teacher_id, activity_id)` 查詢已結束活動
- **THEN** 回傳每題 `question_id`、`display_number`，以及各組 `team_id`、組名、依 `item_id` 對應的答案、受理序號、順位與勝組識別

#### Scenario: 無權限或未結算活動
- **WHEN** 無權教師或任意呼叫者查詢他人活動，或查詢未結束活動
- **THEN** 系統以可辨識的錯誤拒絕，且不洩漏活動結果

### Requirement: 提供 Notes 已結算快照介面
quiz SHALL 將活動資料轉為 Notes writeback DTO，並透過 `NOTES_ENDED_SNAPSHOT(teacher_id, activity_id)` 提供給 Notes；快照的結束與結算旗標須反映活動狀態。（D06、D07、D10、D11）

#### Scenario: 以固定版本建立快照
- **WHEN** 有權教師查詢已結束活動的 Notes 快照
- **THEN** 回傳 `EndedSnapshot`，含活動及教師識別、固定 `import_id`／`import_version`、`closed=True`、`settled=True`，並為固定版本每題提供 `QuestionResult(question_id, winner_id, answers)` 及勝組全部依 `item_id` 排列的 `Answer(item_id, text)`

#### Scenario: 活動尚未結束
- **WHEN** 活動存在、教師有權存取但活動尚未結束
- **THEN** 快照介面回傳 `closed=False`、`settled=False` 的 `EndedSnapshot`，Notes 顯示 `RESULT_NOT_READY`

#### Scenario: 活動不存在或教師無權
- **WHEN** 活動不存在或教師無權存取
- **THEN** 快照介面回傳 `None`，Notes 顯示 `ACTIVITY_NOT_FOUND`

#### Scenario: 無人作答題目快照
- **WHEN** 已結束活動中的題目無有效提交
- **THEN** 該題快照為 `winner_id=None` 且 `answers=()`

### Requirement: 同步作答畫面並保留學生輸入
搶答中教師頁 SHALL 在新答案受理後約 2 秒內顯示最新答案與順位；學生頁輪詢更新 SHALL 保留正在輸入但尚未送出的內容。（R08、本組自行決定）

#### Scenario: 教師即時更新
- **WHEN** 搶答中有新答案成功受理
- **THEN** 教師課堂頁約 2 秒內顯示該答案及更新後順位

#### Scenario: 學生輸入時輪詢
- **WHEN** 學生正在輸入尚未送出的答案且輪詢取得較新活動狀態
- **THEN** 更新狀態時輸入欄內容保持不變

### Requirement: 作答頁提示重送的順位效果
學生作答頁 SHALL 明確提示成功重送會按新的受理時間重新排序。（D01、D02、本組自行決定）

#### Scenario: 題目已送出
- **WHEN** 學生組別已有該題有效提交
- **THEN** 作答頁在該題旁顯示「重新送出會以新的送出時間重新排序」
