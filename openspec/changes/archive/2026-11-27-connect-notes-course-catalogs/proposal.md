# Proposal

## Why

notes 已提供依教師與課程授權的講義清單查詢，但 activities 尚未註冊課程授權，因此教師從自己的課程進入 notes 匯入頁仍可能收到 `NOTES_INTEGRATION_PENDING`。本 change 將兩個模組接通，讓課程講義選擇遵守 D15，並讓教師能從課程頁進入講義管理流程。

## What Changes

- 在應用程式建立時提供 `NOTES_COURSE_ACCESS(teacher_id, course_id) -> bool`，依 activities 的課程所有權授權；測試設定可以覆寫。（D04、D15）
- 非示範模式的課程頁改列 notes 中屬於目前課程的講義版本；加入課程清單關聯時重新驗證該版本屬於目前課程。示範模式仍使用現有示範清單流程。（D11、D15）
- 在活動課程頁加入「匯入／管理講義」入口，連到該課程的 notes 頁。（D15）
- notes 瀏覽器頁面發生 `AppError` 時呈現共用中文錯誤頁、錯誤代碼及返回連結；`/api/` 路徑維持 JSON。`notes.html` 已自行顯示的操作結果維持原樣。（本組自行決定）
- notes 頁加入返回活動課程頁的連結，協助教師完成匯入後回到課程流程。（D15；需告知 A）

### Out of Scope

- 答案提交、順位、結算、結果與 `EndedSnapshot`，由後續 `add-quiz-submission-results` change 負責。（本組自行決定）
- 修改 notes 的匯入、辨識、回填邏輯或 notes 資料表。（D05、D07、D09、D10；本組自行決定）
- CSV 匯出，由 A 負責。（本組自行決定）
- 移除 `GUIDED_NOTES_DEMO_CATALOG=1` 示範模式。（本組自行決定）
- SpecKit 新增的 D13（含準備中）、D18、D19、D22 行為。（本組自行決定；本 change 以作業 PDF 核心功能及已確認的 D04、D11、D15 為範圍）

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `activities`：更新教師課程清單需求，使正式清單依課程範圍授權，並新增 notes 授權接線、匯入入口及瀏覽器錯誤呈現需求。

## Impact

- 影響 `guided_notes/__init__.py`、`guided_notes/activities.py`、`guided_notes/notes.py` 的課程授權介面、notes AppError 處理、`guided_notes/templates/activities_course.html`、`guided_notes/templates/notes.html`，以及相關測試。
- 不修改 notes 的匯入、格式辨識、回填實作或資料表；沿用 `list_course_catalogs(teacher_id, course_id)`，並以別名匯入，避免與 activities 既有同名函式衝突。（D11、D15）
- `notes.html` 增加「回課程頁」連結需告知 A。
- notes 的課程範圍行為既有契約位於尚未 archive 的 `add-guided-notes-import-writeback` change；本 change 只建立 activities delta spec，不建立或修改 app-foundation、guided-notes delta spec。（D15）
