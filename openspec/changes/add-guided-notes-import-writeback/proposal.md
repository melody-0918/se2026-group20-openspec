# Proposal

## Why

教師需要在課程中重複使用 Google Sheets 講義，並在活動結算後把勝組答案填回原表。講義的題數、版面和合併格可能不同，活動也可能使用舊版講義，因此需要動態辨識、固定活動所用版本，以及可確認與重試的回填流程。

## What Changes

### 已確認

- **作業規定 R02、R11／共同決策 D05、D10、D12、D15**　教師先選擇有權限的課程，再從 Google Sheets 匯入、預覽或選用既有講義版本。動態辨識單題及題組，保留題號與順序，分開顯示題數、提交單位數與作答格數。
- **共同決策 D10、D11／本組 Foundation 契約**　正式講義沿用 `list_available_catalogs(teacher_id)` 與 `get_catalog(teacher_id, import_id, import_version)` 的簽章、回傳結構及跨教師拒絕行為。活動建立時固定講義版本、題目與填空識別；改用新版本須另建活動。
- **本組既有實作**　`/notes` Blueprint、教師 session、CSRF、共用 SQLite、OAuth 憑證路徑檢查及示範清單已可沿用。本 Change 補上正式講義與版本持久化。驗收正式講義時關閉 `GUIDED_NOTES_DEMO_CATALOG`。
- **作業規定 R10、R11／共同決策 D06、D07、D09、D10、D11、D14**　從 B 取得已結算結果，將同一勝組的答案寫入原試算表對應格位。略過無勝組題目。來源位置或內容變動時重建預覽，題目集合改變時要求重新匯入。以回讀驗證寫入；重試保留同一勝組，只處理未完成且可安全續寫的格位。
- **共同決策 D01、D02、D08（共同文件 2026-11-26 回報雙組已確認）**　同組同題可主動重送，成功受理才取代舊答案；同一次受理的重試保留原結果。結束前成功受理的有效答案依伺服器受理順序排名，第一名為勝組。這些是 B 的結算規則，A 使用 B 的最終快照。
- **本組技術決定（專案設定）**　Sheets 讀寫使用 Desktop OAuth。教師可獨立執行本機授權；授權失效時提示重新執行授權指令。client 檔及 token 由環境變數指向 repo 外的檔案。

### 待確認

- **D17，暫採 SpecKit 建議值**　沿用來源分頁名稱或自訂講義名稱，顯示來源資訊；多分頁逐一選擇、預覽與保存。
- **D15 課程串接**　保留課程內匯入與選用的需求。待 A／B 確認課程歸屬如何傳遞、由誰篩選清單，以及建立活動時的版本歸屬驗證。
- **D19 題目文字**　共同文件記載題目與小題文字的需求。待 A／B 確認傳遞介面與欄位，現有 Foundation 清單欄位維持原契約。
- **B 的結算介面**　待確認 `get_ended_snapshot()` 的實際接點、歷史活動權限、版本與答案欄位、無勝組表示及結算錯誤回應。D13 的未結束活動限制由 B 依共同文件對齊。

前次 Explore 紀錄和本地設定仍把 D01、D02 排序、D08 列為待確認；本案以 2026-11-26 的共同需求紀錄為準。參照 [共同需求](https://raw.githubusercontent.com/Afra0704/se2026-group20-speckit/master/docs/shared-requirements.md)、[專案設定](../../config.yaml)、[README](../../../README.md)、[Explore 紀錄](../../../docs/explore-notes.md)。

## Capabilities

### New Capabilities

- `guided-notes` — 課程內的 Google Sheets 講義匯入、題目與填空辨識、版本清單，以及將已結算勝組答案安全回填至來源講義。

### Modified Capabilities

## Impact

擴充現有 `notes` Blueprint 與共用 SQLite，提供教師匯入、預覽、版本與回填操作。透過現有兩個清單函式供 B 取用正式講義。課程授權、活動固定版本與結算快照由 A／B 串接。外部依賴為 Google Sheets。參照 [Foundation 主規格](../../specs/app-foundation/spec.md)。

## Out of Scope

- B 負責的 Flask 共用骨架、教師登入、課程及課堂管理、學生介面、活動階段與輪詢、搶答提交、順位、結算與結果公布。
- CSV 結果匯出（待兩組確認，之後另立 Change）。
- D20 教師 Google 登入及 D21 的 Drive 選檔、課程工作區與講義移除（仍待 OpenSpec 同步確認）。
