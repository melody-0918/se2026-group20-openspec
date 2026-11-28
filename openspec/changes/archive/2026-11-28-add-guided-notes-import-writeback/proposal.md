# Proposal

## Why

教師需要在課程中重複使用 Google Sheets 講義，並在活動結算後把勝組答案填回原表。講義的題數、版面和合併格可能不同，活動也可能使用舊版講義，因此需要動態辨識、固定活動所用版本，以及可確認與重試的回填流程。

## What Changes

### 已確認

- **作業規定 R02、R11／共同決策 D05、D10、D12、D15**　教師先選擇有權限的課程，再從 Google Sheets 匯入、預覽或選用既有講義版本。動態辨識單題及題組，保留題號與順序，分開顯示題數、提交單位數與作答格數。
- **共同決策 D10、D11／本組 Foundation 契約**　正式講義沿用 `list_available_catalogs(teacher_id)` 與 `get_catalog(teacher_id, import_id, import_version)` 的簽章、回傳結構及跨教師拒絕行為。活動建立時固定講義版本、題目與填空識別；改用新版本須另建活動。
- **共同決策 D19**　活動建立後，學生可以看到同一固定版本的完整題目文字與題組各小題文字，開始前為唯讀，開始後才能填答。A 只交付題目欄內的純文字及識別碼，來源答案不公開。題組仍整組提交，由 B 負責顯示與操作狀態。
- **本組既有實作**　`/notes` Blueprint、教師 session、CSRF、共用 SQLite、OAuth 憑證路徑檢查及示範清單已可沿用。本 Change 補上正式講義與版本持久化。驗收正式講義時關閉 `GUIDED_NOTES_DEMO_CATALOG`。
- **作業規定 R10、R11／共同決策 D06、D07、D09、D10、D11、D14**　從 B 取得已結算結果，將同一勝組的答案寫入原試算表對應格位。略過無勝組題目。來源位置或內容變動時重建預覽，題目集合改變時要求重新匯入。以回讀驗證寫入；重試保留同一勝組，只處理未完成且可安全續寫的格位。
- **共同決策 D01、D02、D08（共同文件 2026-11-26 回報雙組已確認）**　同組同題可主動重送，成功受理才取代舊答案；同一次受理的重試保留原結果。結束前成功受理的有效答案依伺服器受理順序排名，第一名為勝組。這些是 B 的結算規則，A 使用 B 的最終快照。
- **本組技術決定（專案設定）**　Sheets 讀寫使用 Desktop OAuth。教師可獨立執行本機授權；授權失效時提示重新執行授權指令。client 檔及 token 由環境變數指向 repo 外的檔案。
- **B 正式接入（D15、D19、D06～D11）**　已合入 main 的課程授權、固定版本及 Quiz 結算接線。學生端讀取固定版本文字，教師回填使用正式 `get_ended_snapshot()`。正式 Quiz 結束時即固定結算，沒有獨立的已結束未結算狀態。活動題號無法對應固定版本時，沿用 Provider 的 `404 CATALOG_NOT_FOUND`。Notes 保留對未知或不完整快照的驗證。實測見 [任務紀錄](tasks.md)。

### 待確認

- **D17，暫採 SpecKit 建議值**　沿用來源分頁名稱或自訂講義名稱，顯示來源資訊；多分頁逐一選擇、預覽與保存。

以 2026-11-26 共同需求紀錄及格式契約為對齊基準。D19 的文字交付依共同需求，表頭、題號及答案定位依 Format Contract v1。參照 [共同需求](https://github.com/Afra0704/se2026-group20-speckit/blob/master/docs/shared-requirements.md)、[Guided Notes 格式契約](https://github.com/Afra0704/se2026-group20-speckit/blob/master/specs/001-guided-notes/contracts/format.md)、[專案設定](../../../config.yaml)、[Explore 紀錄](../../../../docs/explore-notes.md)。

## Capabilities

### New Capabilities

- `guided-notes` — 課程內的 Google Sheets 講義匯入、題目與填空辨識、版本清單，以及將已結算勝組答案安全回填至來源講義。

### Modified Capabilities

- `app-foundation` — 保留既有兩個教師範圍查詢與示範模式；課程活動使用新增的授權版本入口。

## Impact

擴充現有 `notes` Blueprint 與共用 SQLite，提供教師匯入、預覽、版本與回填操作。A 的兩個課程清單函式供 B 選用固定版本及顯示題目。課程授權、活動固定版本與結算快照由 A／B 串接。外部依賴為 Google Sheets。參照 [Foundation 主規格](../../../specs/app-foundation/spec.md)、[Foundation 差異規格](specs/app-foundation/spec.md)。

## Out of Scope

- B 負責的 Flask 共用骨架、教師登入、課程及課堂管理、學生介面、活動階段與輪詢、搶答提交、順位、結算與結果公布。
- CSV 結果匯出（待兩組確認，之後另立 Change）。
- D20 教師 Google 登入及 D21 的 Drive 選檔、課程工作區與講義移除（仍待 OpenSpec 同步確認）。
- D22 新加入組別查看歷史結果由 B 負責。SpecKit 006 的移除內建示範模式屬另案，OpenSpec Foundation 既有示範模式維持相容。
