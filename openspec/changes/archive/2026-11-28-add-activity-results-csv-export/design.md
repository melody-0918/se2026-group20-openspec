# Design

## Context

`quiz.get_activity_results(teacher_id, activity_id)` 提供固定活動結果。題目包含 `display_number` 及 `teams`，每筆組別結果包含 `team_name`、`rank`、`is_winner` 及有序的 `answers[{item_id, text}]`。目前教師課堂頁已呈現各活動結果和 Notes 回填入口。CSV 可從同一資料來源下載。

## Goals / Non-Goals

- **Goals**　教師可下載已結束活動的完整結果。維持 CSV 欄位與文字安全，讓使用 Windows Excel 的教師可讀取中文。
- **Non-Goals**　不增設結算方法、資料儲存、學生匯出權限或新的 Notes／OAuth 操作。D19 題目文字仍由既有 API 提供。

## Decisions

- **入口與授權（R01、D04、D06、D14）**　教師課堂頁只在已結束活動的既有結果區旁顯示「下載 CSV」。唯讀 `GET /quiz/api/results/<activity_id>/csv` 沿用 Quiz Blueprint 和 Flask 教師 session。缺教師身分回 `401 TEACHER_REQUIRED`，其餘沿用 `get_activity_results()` 的 `404 ACTIVITY_NOT_FOUND`、`409 RESULT_NOT_READY`。GET 無狀態變更，沿用共用 CSRF 對唯讀方法的處理。回應為附件，使用由活動 ID 組成的檔名與 `Cache-Control: no-store`。不新增 secret 或存取 OAuth，沿用環境變數與教師憑證的既有管理方式。
- **資料投影（D02、D08、D10、D11）**　維持題目、排行及答案的既有順序。用 `item_id` 做小題識別，保留 `display_number`，直接採用 `rank` 和 `is_winner`。每題列出有有效提交的所有組別。無提交的題目保留一列，只有題號欄有值。
- **格式與文字安全（本組決定）**　以標準庫 `csv.writer` 寫入逗號分隔、CRLF、雙引號包裹及 UTF-8 BOM。對文字欄位檢查前置空白、控制字元與中英文公式啟始符號，可疑值在雙引號內加定位字元（tab），依 OWASP 的 Excel 防護建議。前綴是下載檔值的一部分，字串的原內容仍保留在前綴之後。參照 [OWASP CSV Injection](https://community.owasp.org/attacks/CSV_Injection)。

## Risks / Trade-offs

- 用 Excel 開啟是本功能的主要用途。其他程式重新儲存欄位時可能自行轉換文字，防護以系統產生的下載檔為驗證範圍。
- CSV 分支以乾淨 main 為基底。Notes PR #8 和 UI Styling PR #10 的版本交由暫存整合副本重驗。教師頁的唯一改動是已結束活動旁的連結，CSS 維持由 UI Styling 管理。
