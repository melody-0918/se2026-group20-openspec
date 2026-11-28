# Proposal

## Why

目前各頁面缺少一致的字體、留白與表單樣式，投影或錄影時不易閱讀。建立本機共用樣式並整理頁面呈現，可讓教師操作流程、學生作答狀態、notes 與錯誤資訊更清楚，同時維持既有功能行為。

## What Changes

- 新增 `ui-styling` capability，規範所有使用者頁面載入本機共用樣式、狀態文字不得只靠顏色傳達，且不得依賴外部 CSS 或 CDN。（本組自行決定）
- 新增共用 CSS，統一字體、內容寬度、間距、表單、按鈕、清單、卡片、表格與錯誤頁外觀。（本組自行決定）
- 允許在既有元素加上 class、加入純版面容器，以及在各頁 head 引用共用樣式；`notes.html` 可補上正確的 `<head>` 結構。（本組自行決定）
- 不改頁面文字、元素 `id`、表單欄位 `name`、連結網址、JavaScript 邏輯或後端程式。（本組自行決定）
- 新增自動測試確認各頁載入共用樣式且靜態檔可取得；保留既有測試並以示範流程進行人工驗收。（本組自行決定）

## Capabilities

### New Capabilities

- `ui-styling`: 定義使用者頁面的共用樣式載入、基本可讀性及狀態資訊的文字辨識要求。

### Modified Capabilities

無。此 change 不修改 `app-foundation` 或 `activities` 規格。

## Impact

- 預計影響 `guided_notes/templates/` 中的 10 個頁面模板，以及新增的本機共用 CSS 與頁面樣式載入測試。
- `notes.html` 屬於組員 A 負責的 notes 模組；**需告知 A**，再進行該模板的 head 結構與樣式引用調整。只調整呈現層，不更動文案、欄位、網址或功能。
- 使用既有 Flask 靜態檔服務，不新增外部相依、API 或資料變更。
- 工作分支：`feat/improve-ui-styling`。

## Out of Scope

- 變更任何頁面文字、元素 `id`、表單欄位名稱或連結網址。（本組自行決定）
- 修改 JavaScript 邏輯、後端程式、功能、流程或規格行為。（本組自行決定）
- 修改既有測試；本 change 只新增共用樣式引用與靜態檔可取得的自動測試。（本組自行決定）
- 引入外部 CSS 框架、CDN、網路字體或其他網路依賴。（本組自行決定）
- 修改 `app-foundation`、`activities` 或其他既有 capability 規格。（本組自行決定）
