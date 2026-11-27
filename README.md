# se2026-group20-openspec

軟體工程期末專題：Vibe Coding 課堂搶答系統（OpenSpec 組）。此 repo 目前提供本機 Flask 共用骨架、教師登入、notes 題目清單接入點，以及 activities 課程／課堂／活動階段流程。quiz 的作答、順位、結算與結果仍由後續 change 負責。

- 同大組 SpecKit 小組：[Afra0704/se2026-group20-speckit](https://github.com/Afra0704/se2026-group20-speckit)
- 共同需求與決策紀錄：[shared-requirements.md](https://github.com/Afra0704/se2026-group20-speckit/blob/master/docs/shared-requirements.md)

## 技術與模組

使用 Python 3.13、Flask app factory、Jinja、原生 JavaScript、SQLite，只在本機執行。`notes`、`activities`、`quiz` 各自以 Blueprint 掛載。activities 提供教師課程與課程清單關聯、課堂加入碼、學生加入證明、活動階段與狀態同步；notes 已提供 Google Sheets 匯入與回填，尚待與 activities、quiz 正式接線及 archive；答案提交、順位、結算、結果與 CSV 匯出由後續 change 負責。

Foundation 的 `list_available_catalogs(teacher_id)` 和 `get_catalog(teacher_id, import_id, import_version)` 保留既有清單摘要與固定版本題目結構；activities 與 quiz 只能透過這兩個函式取得講義資料，不直接讀取 notes 資料表。摘要含 `import_id`、`import_version`、`title`、`question_count`，完整題目欄位見 [Foundation 規格](openspec/specs/app-foundation/spec.md)；Notes 另提供課程範圍的 `list_course_catalogs()` 和 `get_course_catalog()`，後者可取得固定版本題目與小題文字，正式講義保存在共用 SQLite，使用 `GUIDED_NOTES_DEMO_CATALOG=0` 驗收正式講義，設為 `1` 則所有已登入教師可使用含題組與單題的示範清單。參照 [Notes 整合設計](openspec/changes/add-guided-notes-import-writeback/design.md)。教師登入後由「管理課程與課堂」建立課程，再從課程頁點「匯入／管理講義」進入 notes；匯入後返回課程頁加入該講義版本，再建立課堂及活動，活動固定版本與題目識別。正式模式只顯示該課程已匯入的版本；啟用 `GUIDED_NOTES_DEMO_CATALOG=1` 時可加入示範清單，無需 Google 憑證。課堂各有獨立 6 碼加入碼。同堂正規化後同名組別共用 team，但每個瀏覽器各自取得 HttpOnly 加入證明 cookie，保留 cookie 可在原瀏覽器重新整理後恢復，加入碼或組名不能取代加入證明。教師可在課堂控制頁建立活動並開始或結束活動，同堂最多一個搶答中活動；學生約每秒輪詢，活動顯示順序為搶答中、最新建立的準備中、最近結束，皆無才等候。關課後有效證明仍可查看「課堂已結束」與目前選取活動狀態，活動結果由 quiz change 負責；教師資源權限在後端檢查，狀態變更沿用共用 CSRF 保護。quiz 寫入答案時須在同一 SQLite 連線以 `BEGIN IMMEDIATE` 開啟交易，呼叫 activities 的 `assert_submission_eligible(connection, classroom_id, activity_id, team_id, question_id)`，成功後在同一交易寫入答案並由 quiz 提交；該函式不自行開啟或提交交易，不符合資格時丟出 `AppError`。活動結束與關閉課堂也使用 `BEGIN IMMEDIATE`，讓已提交的結束狀態之後不再受理答案。相關介面與規則見 [活動 change 設計](openspec/changes/archive/2026-11-27-add-classroom-activity-phases/design.md)。

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

在 B 的課程授權接好之前，可從 `python -m flask --app guided_notes:create_app shell` 唯讀檢查一份測試講義。使用包含 `gid` 的分頁連結，下面的檢查會讀取該分頁並輸出題號與作答格數。

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

B 串接 D15 課程授權與已結算活動快照後，以教師身分開啟 `/notes/courses/<course_id>`。分別用單題範本副本和移動過表頭、欄位與題數的題組講義副本匯入、預覽及保存。結算後輸入活動識別碼，核對預覽再確認回填；畫面顯示回讀確認後，在 Google Sheets 核對格位、答案、標號與格式。來源移動或內容變動時先檢查更新後的預覽，無法與固定版本配對時依提示重新匯入。

`pytest` 的 Sheets 與結算測試使用替身。A 側接入點是 `NOTES_COURSE_ACCESS` 與 `NOTES_ENDED_SNAPSHOT`，尚未接入時對應操作會回報整合未就緒。真正的登入、讀寫與人工驗收須另外執行。

## 開發流程

每個功能使用獨立 OpenSpec change 與功能分支：`explore` → `propose` → `apply` → `verify` → `sync` → `archive`。完成 verify 後發 PR，由另一位組員審查；共同需求變動先與 SpecKit 組確認。
