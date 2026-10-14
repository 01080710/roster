---
name: day-end
description: 每天收工：寫開發日誌、更新判斷點、備份資料庫並把當天改動分批 commit（push 前先問）。只在使用者輸入 /day-end 時執行。
disable-model-invocation: true
---

# 收工（/day-end）

目的：把今天的進度、決定與還沒收的事寫下來，讓明天的 /day-start 接得上；並確保程式碼與資料庫都有備份。

## 1. 確認今天做了什麼

- 看這次對話做過的事，再用 `git status --short`、`git diff --stat`、`git log --since=midnight --oneline` 對照實際改動。
- 對話裡做過、但 git 看不到的（例如只討論沒實作、評估後決定不做），也要記。

## 2. 寫日誌 `docs/journal/YYYY-MM-DD.md`

今天已有這個檔案（同一天收工兩次）就**接在後面**，加一個 `## 第 2 次收工 HH:MM` 段落，不要覆蓋。格式：

```markdown
# YYYY-MM-DD 開發日誌

## 完成
- （一項一行：做了什麼、為什麼，附主要檔案；例如「提交班表改為先預覽再寫入，全有或全無（db.py submit_range、routes/roster.py）」）

## 未完成
- （做到一半的、測試沒過的、瀏覽器還沒實測的）

## 明天從這裡開始
1. （最優先的下一步，具體到可以直接動手）

## 測試
- `python -m pytest`：N passed / N failed（今天有改程式就實際跑一次再填，不要沿用舊數字）
```

**個資原則**（日誌會進版控）：不寫員工 email、密碼、請假 / 加班原因、資料庫內容；人用 employee_id 或角色稱呼（例如「Agent」「EMP0003」）。

## 3. 更新判斷點 `docs/decisions.md`

- 今天使用者**拍板**的事 → 加到「已決定」最上面，格式：`- YYYY-MM-DD｜決定內容｜理由`。
- 今天提出、但使用者**還沒決定**的 → 加到「待決定」，寫清楚選項。
- 「待決定」裡今天已經決定的 → 移到「已決定」。
- 只記使用者做的決定，不要把自己的建議寫成已決定。

## 4. 備份資料庫

- 先確認資料庫檔案**存在**：預設 `roster.db`；這台不存在時看 `roster_test.db`（測試環境）。
  `backup_db` 用 `sqlite3.connect` 開檔，檔案不存在會建立一個空的資料庫，所以**檔案不存在就不要執行備份**，跳過並說明。
- 存在時執行：
  - 正式：`python main.py backup`
  - 測試：`ROSTER_DB_PATH=roster_test.db ROSTER_LOG_DIR=test_logs ROSTER_STAGE=test python main.py backup`（PowerShell 用 `$env:ROSTER_DB_PATH = ...` 寫法）
- 回報新備份的檔名。`backups/` 在 .gitignore 裡，不會進版控，這是正確的。

## 5. commit 程式碼

- 先跑一次 `python -m pytest`，結果寫進日誌。測試沒過：照樣可以 commit，但日誌與回報都要寫明，不要隱瞞。
- 把今天的改動**依主題分批 commit**（一個功能一筆）；檔案裡混了不同主題時，拆開再 commit。日誌與 decisions.md 放最後一筆 `docs: day-end YYYY-MM-DD`。
- commit 訊息沿用這個 repo 的風格（英文、小寫開頭、第一行說做了什麼，內文說為什麼），結尾加上系統提示指定的 Co-Authored-By。
- **push 前一定先問使用者**，列出要 push 的 commit，同意才 push。

## 6. 輸出收工摘要

```
## 收工 YYYY-MM-DD
**今天完成**：N 項（列出）
**明天從這裡開始**：（第 1 項）
**待你決定**：N 項
**備份**：DB → backups/<檔名>；git → N 筆 commit（已 push / 等你確認 push）
**測試**：N passed / N failed
```
