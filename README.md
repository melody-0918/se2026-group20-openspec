# se2026-group20-openspec

軟體工程期末專題：Vibe Coding 課堂搶答系統（OpenSpec 組）。此 repo 目前提供本機 Flask 共用骨架、教師登入、notes 題目清單接入點，以及 activities 課程／課堂／活動階段流程。quiz 的作答、順位、結算與結果仍由後續 change 負責。

- 同大組 SpecKit 小組：[Afra0704/se2026-group20-speckit](https://github.com/Afra0704/se2026-group20-speckit)
- 共同需求與決策紀錄：[shared-requirements.md](https://github.com/Afra0704/se2026-group20-speckit/blob/master/docs/shared-requirements.md)

## 技術與模組

使用 Python 3.13、Flask app factory、Jinja、原生 JavaScript、SQLite，只在本機執行。`notes`、`activities`、`quiz` 各自以 Blueprint 掛載。activities 提供教師課程與課程清單關聯、課堂加入碼、學生加入證明、活動階段與狀態同步；答案提交、順位、結算、結果、Google Sheets 匯入／回填與 CSV 匯出由後續 OpenSpec changes 負責。

activities 與 quiz 只能透過 notes 的 `list_available_catalogs(teacher_id)` 和 `get_catalog(teacher_id, import_id, import_version)` 函式取得清單，不直接讀取 notes 資料表。清單摘要含 `import_id`、`import_version`、`title`、`question_count`；題目及作答項目欄位見 `openspec/changes/archive/2026-11-26-add-app-foundation/specs/app-foundation/spec.md`。設定 `GUIDED_NOTES_DEMO_CATALOG=1` 可使用含題組與單題的示範清單；所有已登入教師均可讀取示範資料。activities 將清單版本加入課程，建立活動時固定版本及題目識別。

## 課程、課堂與活動

教師登入後開啟首頁的「管理課程與課堂」：建立課程、加入可用題目清單版本、建立課堂。每間課堂有獨立 6 碼加入碼。學生由首頁「學生加入課堂」輸入加入碼及組名；同堂正規化後同名組別共用 team，但每個瀏覽器都取得自己的 HttpOnly 加入證明 cookie。保留 cookie 可在同一瀏覽器重新整理後恢復；加入碼或組名不等同加入證明。

教師可在課堂頁建立活動，從所屬課程已加入的清單選取；每堂最多一個搶答中活動。學生約每秒輪詢狀態，活動選取順序為搶答中、最新建立的準備中、最近結束；都沒有才等候。關課後有效加入證明仍可讀取「課堂已結束」與目前選取活動狀態，但活動結果由 quiz change 提供。教師資源權限在後端檢查，所有狀態變更沿用共用 CSRF 保護。

quiz 在答案寫入時必須使用同一 SQLite 連線與 `BEGIN IMMEDIATE` 交易呼叫 activities 的 `assert_submission_eligible(connection, classroom_id, activity_id, team_id, question_id)`，成功後在同一交易寫答案並由 quiz 提交；函式會在不符合條件時丟出 `AppError`，且不自行開啟或提交交易。活動結束與關課也使用 `BEGIN IMMEDIATE`，因此提交後的關閉會使後續資格檢查拒絕。

## 環境變數與機敏資料

程式只從環境變數讀取設定。啟動必須設定 `GUIDED_NOTES_SECRET_KEY` 和 `GUIDED_NOTES_DATABASE`；缺少時會指出變數名稱與設定方式。`GUIDED_NOTES_DEMO_CATALOG` 設為 `1` 才啟用示範清單。`.env.example` 僅供參考，不會自動載入，也不能放入真實值。

Google OAuth client 檔與 token 必須存放在 repo 外，notes 實際呼叫 Google Sheets 功能時才需要設定 `NOTES_GOOGLE_CLIENT_SECRETS` 和 `NOTES_GOOGLE_TOKEN`。本 change 尚未實作 Google Sheets 功能。

`.gitignore` 排除 `.env`、`*.sqlite3`、`instance/`、`.venv/`、憑證與 token 檔。請勿將實際密碼、secret key、OAuth 檔案或資料庫加入版本控制。

## Windows cmd：從空白資料庫開始

以下指令需在 repo 根目錄的 Windows cmd 執行。請安裝 Python 3.13，並使用全新的本機資料庫路徑。必要環境變數只對目前 cmd 視窗有效；開另一個視窗啟動伺服器時，需再次設定。

```bat
cd C:\path\to\se2026-group20-openspec
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" -m venv .venv
) else (
  py -3.13 -m venv .venv
)
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .[dev]

set "GUIDED_NOTES_SECRET_KEY=replace-with-a-random-local-secret"
set "GUIDED_NOTES_DATABASE=instance\local.sqlite3"
set "GUIDED_NOTES_DEMO_CATALOG=1"

python -m flask --app guided_notes:create_app init-db
python -m flask --app guided_notes:create_app auth create-teacher teacher1
python -m flask --app guided_notes:create_app run
```

建立帳號時，命令會提示輸入兩次密碼，輸入不會顯示在畫面上。密碼不能放在命令參數中；兩次輸入不一致時不會建立帳號，請重新執行命令。成功啟動後，在瀏覽器開啟 `http://127.0.0.1:5000/`，選擇「教師登入」。

執行測試（同一 cmd 視窗、已啟用 `.venv`）：

```bat
python -m pytest
```

若只想關閉示範清單，可設定 `set "GUIDED_NOTES_DEMO_CATALOG=0"`。notes 使用 Google Sheets 時，請在 cmd 設定 repo 外的 OAuth 檔案路徑，例如：

```bat
set "NOTES_GOOGLE_CLIENT_SECRETS=C:\private\google-client.json"
set "NOTES_GOOGLE_TOKEN=C:\private\google-token.json"
```

## 開發流程

每個功能使用獨立 OpenSpec change 與功能分支：`explore` → `propose` → `apply` → `verify` → `sync` → `archive`。完成 verify 後發 PR，由另一位組員審查；共同需求變動先與 SpecKit 組確認。
