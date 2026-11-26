# se2026-group20-openspec

軟體工程期末專題 - 課堂搶答系統（OpenSpec 組）

老師匯入 Google Sheets 的填空式學習單（Guided Notes），開啟與結束搶答；學生以組別為單位送出答案，最快送出的組別為該題勝組；搶答結束後，老師可把勝組答案回填到原本的學習單。

- 同大組 SpecKit 小組：[Afra0704/se2026-group20-speckit](https://github.com/Afra0704/se2026-group20-speckit)
- 共同需求與決策紀錄：[shared-requirements.md](https://github.com/Afra0704/se2026-group20-speckit/blob/master/docs/shared-requirements.md)
- 繳交期限：2026-11-30 00:00（Asia/Taipei）

## 技術堆疊

與 SpecKit 組一致：Python 3.13、Flask、Jinja、原生 JavaScript、SQLite，前端約每 1 秒輪詢同步。Google Sheets 使用官方 API 與 OAuth Desktop app 授權。

## 分工

| 角色 | 成員 | 主責 | 互審與人工驗收 |
| --- | --- | --- | --- |
| A | （待填） | notes：Guided Notes 匯入、辨識與回填；額外功能 CSV 匯出 | 審查 B 的活動階段、同時提交與截止邊界 |
| B | （待填） | activities 與 quiz：身分、活動階段、課程與課堂、作答提交、順位與結算 | 使用不同版面的講義驗收 A 的動態辨識與回填 |
| 雙方 | | 共用資料介面、整合、Demo、交件與 AI 對話紀錄 | 互審 PR，交叉執行人工驗收 |

## 開發流程

1. 每個功能使用一個 OpenSpec change：`/openspec explore` → `propose` → `apply` → `verify` → `sync` → `archive`。
2. 每個 change 開一個功能分支，完成 verify 後發 PR。
3. `main` 受保護：PR 需另一位組員 Approve 後才能合併。
4. 功能或規則有變動時，先與 SpecKit 組確認，並更新共同需求文件。

## Google Sheets 授權（機敏資料不可進 repo）

OAuth client 檔與 token 必須放在 **repo 外**的私人資料夾，用環境變數指定路徑：

```bat
set "NOTES_GOOGLE_CLIENT_SECRETS=C:\your-private-folder\client.json"
set "NOTES_GOOGLE_TOKEN=C:\your-private-folder\token.json"
```

詳細的 Google Cloud 設定步驟，待 notes 模組完成後補上。
