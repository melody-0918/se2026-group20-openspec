# se2026-group20-openspec

軟體工程期末專題：Vibe Coding 課堂搶答系統（OpenSpec 組）。此 repo 目前提供本機 Flask 共用骨架、教師登入，以及 notes、activities、quiz 模組接入點。

- 同大組 SpecKit 小組：[Afra0704/se2026-group20-speckit](https://github.com/Afra0704/se2026-group20-speckit)
- 共同需求與決策紀錄：[shared-requirements.md](https://github.com/Afra0704/se2026-group20-speckit/blob/master/docs/shared-requirements.md)

## 技術與模組

使用 Python 3.13、Flask app factory、Jinja、原生 JavaScript、SQLite，只在本機執行。`notes`、`activities`、`quiz` 各自以 Blueprint 掛載。課程、課堂、加入碼、學生加入、活動流程、同步、作答、順位、結算、Google Sheets 匯入／回填與 CSV 匯出由後續 OpenSpec changes 負責。

activities 與 quiz 只能透過 notes 的 `list_available_catalogs(teacher_id)` 和 `get_catalog(teacher_id, import_id, import_version)` 函式取得清單，不直接讀取 notes 資料表。清單摘要含 `import_id`、`import_version`、`title`、`question_count`；題目及作答項目欄位見 `openspec/changes/add-app-foundation/specs/app-foundation/spec.md`。設定 `GUIDED_NOTES_DEMO_CATALOG=1` 可使用含題組與單題的示範清單；所有已登入教師均可讀取示範資料。一般清單的持久化及匯入由後續 notes change 實作；課程範圍依 D15 留待後續 change 擴充。

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
