# Tasks

## 1. 專案結構與設定

- [ ] 1.1 建立單一 Python 套件、Flask app factory 與 `notes`、`activities`、`quiz` 子模組骨架；以匯入檢查及建立 app 的 smoke test 驗證 Blueprint 可掛載。
- [ ] 1.2 加入 Python 3.13 所需依賴與 pytest 開發依賴，以及 `.env.example`；檢查範例只含虛構值，並以缺少 `GUIDED_NOTES_SECRET_KEY` 或 `GUIDED_NOTES_DATABASE` 的啟動測試確認錯誤列出變數及設定方式。
- [ ] 1.3 實作 Google 設定延遲檢查；以未設定 `NOTES_GOOGLE_CLIENT_SECRETS`、`NOTES_GOOGLE_TOKEN` 啟動 app 的測試確認可啟動，並以 notes Google 功能呼叫測試確認錯誤清楚指出缺漏路徑設定。

## 2. 資料庫

- [ ] 2.1 建立共用 SQLite schema 與初始化命令；以新的空白 `GUIDED_NOTES_DATABASE` 執行命令，確認資料庫及 schema 建立成功，重複執行結果明確。
- [ ] 2.2 建立教師資料儲存與命令列帳號建立功能；確認密碼不接受命令參數、以不回顯提示輸入並再次確認；以 pytest 驗證成功建立後密碼以雜湊保存、重複帳號得到明確錯誤，且密碼不一致時提示重新執行並確保資料庫未新增資料。

## 3. 教師登入與 CSRF

- [ ] 3.1 實作教師登入、session cookie、登入保護及登出；以 pytest 驗證正確密碼成功、錯誤密碼採一般訊息、未登入教師頁導向登入頁，以及登出後存取被拒。
- [ ] 3.2 保護所有狀態變更請求免受 CSRF；以 pytest 驗證缺少或錯誤 token 的請求不改變狀態，有效 token 的請求可正常處理。
- [ ] 3.3 統一可預期錯誤回應的 `code` 與 `message` 欄位；以 pytest 驗證 HTTP 回應及模組介面錯誤均符合共用格式。

## 4. Blueprint 掛載點與首頁

- [ ] 4.1 完成首頁、教師登入入口、尚未開放的學生加入入口及受保護的空白教師頁；以 Flask 測試 client 驗證首頁入口文字與路由行為。
- [ ] 4.2 註冊 `notes`、`activities`、`quiz` 三個 Blueprint，並提供 notes 空白頁；以 app 路由清單與測試 client 確認三個模組均可掛載且 notes 頁可讀取。

## 5. 題目清單介面與示範資料

- [ ] 5.1 實作 `list_available_catalogs(teacher_id)` 與 `get_catalog(teacher_id, import_id, import_version)`；以 pytest 驗證摘要包含 `import_id`、`import_version`、`title`、`question_count`，清單與題目欄位、型別及來源順序符合契約，未知或其他教師不可存取的清單回報穩定錯誤且不洩漏清單存在性。
- [ ] 5.2 加入 `GUIDED_NOTES_DEMO_CATALOG=1` 示範模式；以 pytest 驗證任何已登入教師都能透過兩個函式讀取同一份示範資料，至少包含一個題組、兩個單題，並驗證摘要及每題／item 的識別、標號、類型與順序欄位（單題恰有一個 item）。
- [ ] 5.3 在介面文件及模組依賴規則中說明 activities／quiz 只能呼叫 notes 兩個公開函式；以程式碼檢查確認消費模組沒有直接讀取 notes 資料表的依賴。

## 6. 測試

- [ ] 6.1 建立 pytest 自動驗收，涵蓋空白資料庫初始化、教師帳號建立及密碼不一致不新增資料、正確／錯誤密碼登入、教師頁保護、登出、缺少必要環境變數、Google 路徑延遲檢查、教師範圍題目清單介面、錯誤格式及示範資料；以 `python -m pytest` 確認全數通過且測試使用臨時空白資料庫。
- [ ] 6.2 檢查版本控制追蹤內容及新增檔案，確認沒有真實密碼、secret key、OAuth client 檔或 token，並確認 `.env.example` 只有範例值；以 `git status`、追蹤檔清單及人工檢視完成驗證。

## 7. README

- [ ] 7.1 更新 README，記錄環境變數用途、必要設定錯誤處理、教師範圍題目清單契約、教師帳號密碼以不回顯方式輸入及 Google 憑證放在 repo 外的方式；逐項比對文件與實際命令及環境變數名稱，確認密碼不會出現在命令參數範例。
- [ ] 7.2 補上 Windows cmd 從建立虛擬環境、安裝套件、設定環境變數、初始化新的空白資料庫、建立教師帳號、啟動伺服器到執行 pytest 的完整指令；人工依 README 在 Windows cmd 從空白資料庫完整操作一次，確認密碼以隱藏提示輸入並再次確認、登入與登出可用、測試通過，且操作不需要真實 Google 憑證。
