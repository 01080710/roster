# docs/：開發紀錄

| 檔案 | 內容 | 誰會讀寫 |
|---|---|---|
| [case-studies.md](case-studies.md) | 開發案例：每個案例用紅（問題）、藍（決策）、綠（成果）呈現 | 給面試官、新加入的開發者 |
| [decisions.md](decisions.md) | 判斷點：已決定（日期、內容、理由）與待決定的事項 | `/day-start` 讀、`/day-end` 更新 |
| [journal/](journal/) | 開發日誌，每天一份 `YYYY-MM-DD.md`：完成、未完成、明天從這裡開始、測試結果 | `/day-end` 寫入 |

系統本身的設計（業務流程、資料表、權限、備份與日誌）見根目錄的 [structure.md](../structure.md)。

## 開工 / 收工指令

在 Claude Code 裡輸入（定義在 [.claude/skills/](../.claude/skills/)）：

- `/day-start`：讀最新日誌與判斷點、檢查 git 與資料庫備份，整理今天從哪裡接手。只讀不寫。
- `/day-end`：寫日誌、更新判斷點、備份資料庫，依主題分批 commit；push 前會先詢問。

## 個資原則

這個資料夾會進版控，**不寫**員工 email、密碼、請假 / 加班原因或資料庫內容；人用 employee_id 或角色稱呼（例如「EMP0003」「Agent」）。
