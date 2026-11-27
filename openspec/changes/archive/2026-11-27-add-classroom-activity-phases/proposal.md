# Proposal

## Why

共用骨架已有教師登入、資料庫及模組掛載點，但教師尚不能建立課程與課堂，也沒有學生加入、活動階段或同步狀態。此 change 提供 quiz 作答功能所需的課程脈絡、學生組別與活動生命週期，並建立可安全判定送出資格的跨模組介面。

## What Changes

- 新增教師管理課程、在課程加入可存取題目清單，以及建立課堂的能力。（D04、D12、D15）
- 新增課堂加入碼、學生組別建立／重用及以加入證明恢復個別瀏覽器授權的流程。（D04、D09、D12）
- 新增活動建立與「準備中 → 搶答中 → 已結束」階段控制；每堂最多一個搶答中活動，關閉課堂會結束進行中活動並禁止新活動或開始操作。（D03、D13、D14）
- 新增教師及學生狀態頁面與輪詢，依「搶答中 → 最新建立的準備中 → 最近結束 → 等候」選取學生目前活動；關課後仍讓有效加入證明的學生查看課堂結束狀態與最近活動階段。（R08、D03、D12、D14；D16 結果查看由 quiz change 負責）
- 新增供 quiz 在答案寫入交易中呼叫的送出資格判定介面，固定檢查活動階段、課堂組別及活動題目集合。（D02、D11、D13）
- 不提供課程、課堂或活動刪除功能。

### Out of Scope

- 送出答案、順位、結算與結果頁。（D06、D16；後續 quiz change）
- Guided Notes 匯入、回填與 CSV 匯出。（後續 notes／CSV change）

## Capabilities

### New Capabilities
- `activities`: 教師課程與清單關聯、課堂加入及組別、活動階段、狀態同步與 quiz 送出資格判定。

### Modified Capabilities
- 無。共用 app-foundation 與 notes 函式契約維持不變。

## Impact

- 影響 `guided_notes/activities.py`、SQLite schema、教師與學生頁面及其狀態 API；沿用既有 Flask、Jinja、原生 JavaScript、SQLite、教師 session 與 CSRF 保護。
- activities 透過 notes 的 `list_available_catalogs(teacher_id)` 與 `get_catalog(teacher_id, import_id, import_version)` 取得清單，不直接讀取 notes 資料表。（D11、D15）
- quiz 透過 activities 的資格判定及交易介面確認答案受理條件；結束活動與關閉課堂與答案寫入以同一資料庫交易序列化。（D02、D13、D14）
- 規則來源：課程與課堂流程依 D12／FR-001、D04、D03、D09、D11、D13、D14、D15；同步依 R08；其他格式細節依本組自行決定的合理預設。
