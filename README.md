# se2026-group20-openspec

軟體工程期末專題：Vibe Coding 課堂搶答系統（OpenSpec 組）。此 repo 提供本機 Flask 共用骨架、教師登入、Guided Notes 匯入與回填、課程／課堂／活動階段，以及 quiz 作答、順位、結算與結果。

- 同大組 SpecKit 小組：[Afra0704/se2026-group20-speckit](https://github.com/Afra0704/se2026-group20-speckit)
- 共同需求與決策紀錄：[shared-requirements.md](https://github.com/Afra0704/se2026-group20-speckit/blob/master/docs/shared-requirements.md)

## 技術與模組

使用 Python 3.13、Flask app factory、Jinja、原生 JavaScript、SQLite，只在本機執行。`notes`、`activities`、`quiz` 各自以 Blueprint 掛載。activities 提供教師課程與課程清單關聯、課堂加入碼、學生加入證明、活動階段與狀態同步；notes 提供 Google Sheets 匯入與回填，並透過 `NOTES_COURSE_ACCESS` 與 activities 完成課程授權接線。quiz 提供按題號整組提交、成功重送、受理順位、教師與學生結果，以及 Notes 結算快照（`NOTES_ENDED_SNAPSHOT`）。CSV 匯出本身由組員 A 負責。

Foundation 的 `list_available_catalogs(teacher_id)` 和 `get_catalog(teacher_id, import_id, import_version)` 提供固定版本題目結構；quiz 不直接讀 Notes 資料表。正式模式另使用 `get_course_catalog()` 取得題目及小題顯示文字；示範模式只顯示題號與小題標號。摘要欄位與題目結構見 [Foundation 規格](openspec/specs/app-foundation/spec.md)。正式講義可用 `GUIDED_NOTES_DEMO_CATALOG=0` 驗收，設為 `1` 則可用含題組與單題的示範清單，無需 Google 憑證。參照 [Notes 整合設計](openspec/changes/add-guided-notes-import-writeback/design.md)。教師登入後建立課程、匯入或選取講義版本，加入課程後建立課堂及活動；活動固定題目版本。課堂各有獨立加入碼。同堂正規化後同名組別共用 team，但各瀏覽器以 HttpOnly 加入證明 cookie 恢復原組別。教師可在課堂控制頁建立、開始或結束活動，同堂最多一個搶答中活動；學生約每秒輪詢，活動顯示順序為搶答中、最新建立的準備中、最近結束，皆無才等候。準備中學生可看固定版本題目，搶答中可填答。每題或題組須一次填妥所有答案，每小題不得空白且上限 200 字；同組成功重送會取代答案並重新排序，同次請求重試則不重複受理。教師可在頁面查看答案與順位，活動結束後檢視勝組並透過活動識別碼進入同課程 Notes 回填。學生搶答中只看到自己的送出狀態，結束後看到勝組答案及自己組答案／順位；關課後只顯示「課堂已結束」。quiz 寫入答案時在同一 SQLite 連線以 `BEGIN IMMEDIATE` 開啟交易，先呼叫 activities 的 `assert_submission_eligible(connection, classroom_id, activity_id, team_id, question_id)`，再在同一交易寫入；資格拒絕時不改變舊答案。活動結束及關閉課堂也使用 `BEGIN IMMEDIATE`，確保只有結束前受理的答案進入結果。相關介面與規則見 [活動 change 設計](openspec/changes/archive/2026-11-27-add-classroom-activity-phases/design.md)。

## 環境變數與機敏資料

程式只從環境變數讀取設定。啟動必須設定 `GUIDED_NOTES_SECRET_KEY` 和 `GUIDED_NOTES_DATABASE`；缺少時會指出變數名稱與設定方式。`GUIDED_NOTES_DEMO_CATALOG` 設為 `1` 才啟用示範清單。`.env.example` 僅供參考，不會自動載入，也不能放入真實值。

Google OAuth client 檔與 token 必須存放在 repo 外。Notes 呼叫 Google Sheets 或執行本機授權時會讀取 `NOTES_GOOGLE_CLIENT_SECRETS` 與 `NOTES_GOOGLE_TOKEN`，啟動程式和讀取已保存的講義版本只需要共用設定。

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

## Notes 人工授權與驗收

在同一個 cmd 視窗關閉示範清單，並確認兩個 OAuth 環境變數已指向 repo 外的不同檔案。以下路徑是占位範例，已有設定可以沿用。

```bat
set "GUIDED_NOTES_DEMO_CATALOG=0"
set "NOTES_GOOGLE_CLIENT_SECRETS=C:\private\google-client.json"
set "NOTES_GOOGLE_TOKEN=C:\private\google-token.json"
python -m flask --app guided_notes:create_app init-db
python -m flask --app guided_notes:create_app notes authorize-sheets
```

`init-db` 會補上 Notes 資料表並保留既有教師帳號。授權指令會開啟瀏覽器，請使用已列為測試使用者且能存取講義的 Google 帳號。授權成功後 token 會存到指定路徑。收到重新授權提示時，再執行同一指令。匯入和回填的 HTTP 請求不會開啟 Google 登入。

教師可從活動課程頁點選「匯入／管理講義」，進入 `/notes/courses/<course_id>` 匯入講義。若不經網頁、只想快速檢查講義能否辨識，也可從 `python -m flask --app guided_notes:create_app shell` 唯讀檢查一份測試講義。使用包含 `gid` 的分頁連結，下面的檢查會讀取該分頁並輸出題號與作答格數。

```python
from guided_notes.notes_format import parse_layout
from guided_notes.notes_sheets import GoogleSheets, source_from_link

spreadsheet_id, tab_id = source_from_link(input("測試講義分頁連結："))
sheets = GoogleSheets()
if tab_id is None:
    print(sheets.tabs(spreadsheet_id))
    tab_id = int(input("分頁 sheetId："))
questions = parse_layout(sheets.read(spreadsheet_id, tab_id))
print([(question["display_number"], len(question["items"])) for question in questions])
```

課程授權已接通，可直接從活動課程頁進入 `/notes/courses/<course_id>` 匯入講義。分別用單題範本副本和移動過表頭、欄位與題數的題組講義副本匯入、預覽及保存。活動結束後，教師課堂頁會顯示活動識別碼及該課程 Notes 入口；輸入活動識別碼後核對預覽，再確認回填。畫面顯示回讀確認後，在 Google Sheets 核對格位、答案、標號與格式。來源移動或內容變動時先檢查更新後的預覽，無法與固定版本配對時依提示重新匯入。

`pytest` 的 Sheets 與結算測試使用替身。`NOTES_COURSE_ACCESS` 由 activities 註冊；`NOTES_ENDED_SNAPSHOT` 由 `create_app` 註冊為 quiz 的 `get_ended_snapshot(teacher_id, activity_id)` adapter。真正的 Google Sheets 登入、讀寫與人工驗收須另外執行。

## 開發流程

每個功能使用獨立 OpenSpec change 與功能分支：`explore` → `propose` → `apply` → `verify` → `sync` → `archive`。完成 verify 後發 PR，由另一位組員審查；共同需求變動先與 SpecKit 組確認。
