# Proposal

## Why

教師在活動結束後需要帶走各組答案、順位與勝組，以便在課堂講評或後續整理。正式 Quiz 已提供固定結算結果，CSV 以同一份資料產生可下載的結果檔。

## What Changes

- **R01、R04、R07／D04、D06、D08、D14**　只有有權管理該活動的已登入教師才能下載。教師可從已結束活動的結果區下載，包括關課後的歷史活動。
- **D02、D08、D10、D11**　依活動固定結果匯出所有已受理的有效組別答案與順位。題組每個填空一列，整組共用順位及勝組判定。無人作答的題目保留題號及一列空白結果。
- **本組決定（課程額外功能）**　CSV 使用中文欄位、逗號分隔、標準跳脫及 UTF-8 BOM，並在匯出時保護可能被 Excel 視為公式的文字。共同需求將 CSV 列為待雙組確認的額外功能，本 Change 依 OpenSpec 組本次確認的交付範圍實作。參照 [共同需求](https://github.com/Afra0704/se2026-group20-speckit/blob/master/docs/shared-requirements.md)。

## Capabilities

### New Capabilities

- `activity-results-csv-export` — 教師下載已結束活動的完整結算 CSV。

### Modified Capabilities

## Impact

Quiz Blueprint 增加一個下載入口，讀取既有 `get_activity_results(teacher_id, activity_id)`。教師課堂活動頁在已結束活動旁新增下載連結。CSV 使用 Python 標準函式庫，無新套件或資料庫遷移。

## Out of Scope

- Quiz 提交、順位、結算、結果資料契約及 D19 文字。
- Guided Notes 匯入、回填、既有封存及其規格。
- 學生下載、未結束活動匯出、多活動合併匯出及 Excel 活頁簿。
