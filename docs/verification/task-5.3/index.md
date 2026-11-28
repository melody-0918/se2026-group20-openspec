# Task 5.3 去識別化驗收證據

OpenSpec Change `add-guided-notes-import-writeback`。驗收日期為 2026-11-28（台北時間）。真實 A/B 驗收在 `test/notes-quiz-e2e` 的 `f13e0cd` 執行，由 A 模組成員（人工驗收執行者）操作。講義為 A02 混合版面版本 1。

| 截圖檔名 | 驗收步驟 | 可證明的測試結果 |
| --- | --- | --- |
| [01-import-preview.png](./01-import-preview.png) | A02 講義匯入預覽 | 確認 3 題、3 個提交單位、5 個答案格及題號 3、08、12。 |
| [02-saved-version.png](./02-saved-version.png) | 講義版本保存及加入課程 | 課程清單中可見 A02-混合版本 1。 |
| [03-activity-preparation.png](./03-activity-preparation.png) | 課堂與活動建立 | 教師頁可見課堂及處於準備中的活動，列出三個題號。 |
| [04-both-teams-joined.png](./04-both-teams-joined.png) | 兩組學生加入 | 教師頁列出紅隊、藍隊，活動仍處於準備中。 |
| [05-red-team-read-only.png](./05-red-team-read-only.png) | 紅隊準備中畫面 | 紅隊可閱讀完整題目與小題，沒有作答欄。 |
| [06-blue-team-read-only.png](./06-blue-team-read-only.png) | 藍隊準備中畫面 | 藍隊可閱讀完整題目與小題，沒有作答欄。 |
| [07-red-team-group-submit.png](./07-red-team-group-submit.png) | 紅隊搶答中畫面 | 題組兩個小題各有答案欄，並共用一個送出按鈕。 |
| [08-blue-team-group-submit.png](./08-blue-team-group-submit.png) | 藍隊搶答中畫面 | 題組兩個小題各有答案欄，並共用一個送出按鈕。 |
| [09-live-ranks.png](./09-live-ranks.png) | 搶答中三題雙組排行 | 教師頁可見兩隊的三題答案及暫列順位。 |
| [10-official-quiz-results.png](./10-official-quiz-results.png) | Quiz 正式結算 | 已結束，題號 3 紅隊勝出，題號 08、12 藍隊勝出，兩組排行與答案可核對。 |
| [11-notes-writeback-preview.png](./11-notes-writeback-preview.png) | Notes 正式回填預覽 | 五個格位及勝組答案皆列出，狀態為等待確認，略過 0 題。 |
| [12-original-sheets-writeback.png](./12-original-sheets-writeback.png) | 原 T53 Google Sheets 回填結果 | N10 紅色、N12 圓形、M14 香蕉、N16 貓、N17 台中，題號與小題標號可見。 |
| [13-notes-verified.png](./13-notes-verified.png) | Notes 正式回填結果 | 五個目標格全部已回讀確認，略過 0 題。 |
| [14-format-copy-before.png](./14-format-copy-before.png) | 格式保全補驗寫入前 | 獨立副本中的五個目標格空白，題號、題目、小題標號與作答版面可供對照。 |
| [15-format-copy-after.png](./15-format-copy-after.png) | 格式保全補驗回填後 | 五個答案已顯示並靠左，字詞清楚，合併版面及標號可供目視對照。 |

`01` 至 `13` 為真實 A/B 驗收。教師與兩組學生完成匯入、準備、搶答、Quiz 正式結算及 Notes 回填。截圖保留作答與結算結果。

`14` 與 `15` 為獨立副本的格式保全補驗，使用人工 `EndedSnapshot`。截圖記錄寫入前後的目視結果。既有獨立 API 比對確認 25,995 個非目標格的原值、顯示值、`userEnteredFormat` 和 `effectiveFormat` 皆一致，15 個合併範圍一致，五個目標格的 `userEnteredFormat` 一致。五個目標格共 10 項 `effectiveFormat` 差異，`horizontalAlignment` 由未回傳變為 `LEFT`，`hyperlinkDisplayType` 由未回傳變為 `PLAIN_TEXT`。人工審閱已接受本次差異，原始嚴格檢查結果保留 `REVIEW_REQUIRED`。

PNG 已裁切或以不透明遮蔽後重新編碼，只保留驗收所需畫面。索引及截圖可獨立閱讀。
