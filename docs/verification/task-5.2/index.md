# Task 5.2 去識別化驗收證據

驗收日期為 2026-11-28（台北時間）。真實 Sheets 案例由 Codex 依使用者授權執行，正式 Notes 路由使用獨立 SQLite、固定講義版本 1 及人工 `EndedSnapshot`。真實來源僅為 `T52-A07-專用驗收`，五個分頁均已核對初始格值與合併範圍。

## 真實 Sheets 驗收

| 情境 | HTTP 與回填批次 | 獨立 API 回讀 |
| --- | --- | --- |
| 無勝組 `skip` | 200，兩格 `verified`，略過 1 題。Notes 共一筆回填批次。 | D2 保留 `T52-KEEP`，E3 為 `T52-WIN-1`，E4 為 `T52-WIN-2`。非目標格及六個合併範圍一致。 |
| 移動欄列 `move` | 409 `SOURCE_PREVIEW_STALE`，`source_changed`，零回填批次。 | E3 保留 `T52-KEEP`，新版目標 F4、F5 空白。 |
| 修改原值 `value` | 409 `SOURCE_PREVIEW_STALE`，`source_changed`，零回填批次。 | 新預覽識別出 E3 的 `T52-EXTERNAL-BEFORE`。拒絕後 E3 保留該值，E4 空白。 |
| 修改題幹 `text` | 409 `SOURCE_PREVIEW_STALE`，`source_changed`，零回填批次。 | B3 保留 `T52-EDITED-PROMPT`，E3、E4 空白。 |
| 移除題目 `remove` | 409 `SOURCE_REIMPORT_REQUIRED`，零回填批次。 | 剩餘答案格 E2、E3 空白，活動仍固定版本 1。 |

四個 A07 案例在測試來源異動後各提交一次舊預覽。獨立 API 回讀確認，拒絕後的整本試算表與提交前的狀態一致。重建的預覽 ID 與舊 ID 不同，仍待確認。逐案 HTTP、格值、回填批次與生效格式差異收錄在 [真實驗收紀錄](./live-results.json)。

## 沿用的 A08 證據

- [外部改值衝突](./a08-conflict.png)　既有人工替身驗收中，首次部分完成後回 `502 SHEETS_WRITE_UNVERIFIED`。注入外部改值後沿用同一預覽，回 `409 WRITEBACK_CONFLICT`，E3 為 `verified`、E4 為 `conflict`。外部值保留及零新增批次另由既有自動化測試斷言。
- [中斷後只補未完成格](./a08-retry.png)　既有人工替身驗收的終端紀錄顯示首次只完成 E3，重試只補 E4，兩格均可回讀，再次確認沒有第三筆批次。整批已寫但回讀中斷的情境另有既有自動化測試。

使用者同意上述證據組合。附圖保留受控替身人工操作結果，網址及活動、預覽識別碼已遮蔽。
