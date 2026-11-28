# Proposal

## Why

目前 quiz 只有 Blueprint 掛載點，無法讓學生依組別提交答案，也無法提供搶答順位、結算結果或回填快照。此 change 實現課堂搶答的作答到結算流程，並提供 A 使用的結果查詢介面。

## What Changes

- **共同決策 D01、D02、D08、D10**　新增依主題號整組提交、伺服器受理序號、成功重送取代舊答案、順位及勝組結算；拒收的重送保留舊答案。相同內容的主動重送仍取得新受理序號。
- **共同決策 D02、本組自行決定**　送出在即時交易中先檢查資格；同一組、活動、主題號及送出識別碼相符時重播原受理結果，識別碼不授權查詢他組資料。
- **共同決策 D06、D08、D22（取代 D16）、本組決定；作業規定 R08**　新增教師即時及結束後結果、學生結束後受限結果查詢；關課後學生頁只顯示「課堂已結束」。教師課堂頁在活動結束後提供活動識別碼及 Guided Notes 回填入口。
- **共同決策 D11、D19／Foundation 契約**　依活動固定版本取得題目及小題結構；正式模式使用 `get_course_catalog` 取得文字，示範模式使用 `get_catalog` 並只顯示題號與小題標號。開始前唯讀看題，搶答開始後作答，來源答案與來源資訊不交付學生。
- **共同決策 D07、D10、D11／回填介面契約**　提供固定結算快照並於 `create_app` 註冊 `NOTES_ENDED_SNAPSHOT`，以及 `get_activity_results(teacher_id, activity_id)` 給 CSV 匯出使用。
- **作業規定 R08、本組自行決定**　教師頁於搶答中有新受理答案後約 2 秒內顯示內容與順位；學生輪詢不清除尚未送出的輸入。作答頁提示重送會重新排序。
- **Out of Scope — 本次明確排除**　D13「準備中也算未結束活動」限制及加入碼格式。
- **Out of Scope — A 負責／待與 A 確認**　CSV 匯出本身由 A 負責；本 change 提供查詢函式，CSV 欄位需與 A 確認。
- **Out of Scope — 本次明確排除**　更公平的順位機制、計時器、答案正誤判斷與刪除答案。
- **合理預設**　拒絕空白答案及超過 200 字的小題答案；題組須全部填答；同一送出識別碼僅在同組、同活動、同主題號範圍內重播。錯誤訊息使用中文。

## Capabilities

### New Capabilities

- `quiz`: 按組提交答案、順位與勝組結算、權限隔離的結果查詢，以及提供 CSV 與 Notes 回填使用的結果介面。

### Modified Capabilities

- `activities`: 調整課堂關閉後學生頁的顯示規則，並增加教師已結束活動的識別碼與回填入口。

## Impact

- 影響 `guided_notes/quiz.py`、activities 的學生／教師狀態 API 與課堂頁、`create_app` 的 Notes 快照註冊，以及 quiz 持久化 schema；不修改 activities 資料表。
- quiz 依 activities 的 `immediate_transaction`、`assert_submission_eligible` 和伺服器端課堂／課程關聯取得資格及教師身分；依 Notes `get_catalog` 和 `notes_writeback` DTO 取得固定 item 結構與回填快照。
- 對 A 提供 `get_activity_results(teacher_id, activity_id)`；需與 A 確認 CSV 欄位。
- 順位採受理序號，重送會改變順位；學生與教師結果欄位依活動階段和課堂狀態分流。
