# static/：樣式與前端程式

不使用前端框架與建置工具：原生 JS + 一份 CSS，直接由 Flask 提供。因為 CSP 不允許 inline script，頁面上所有行為都寫在這裡。

| 檔案 | 載入的頁面 | 內容 |
|---|---|---|
| [theme.js](theme.js) | 全部（放在 `<head>`） | 畫面繪出前套用亮色 / 深色主題，避免閃爍 |
| [base.js](base.js) | 全部 | 主題切換、登入有效時間、`data-confirm`、`data-autosubmit`、彈窗關閉、主管取消已核准申請的彈窗 |
| [roster.js](roster.js) | 排班總覽 | 逐日明細彈窗、帶入預設班別、提交班表的預覽彈窗、修改彈窗 |
| [leave.js](leave.js) | 請假 | 請假月曆、即時預覽請假天數 |
| [overtime.js](overtime.js) | 加班 | 依方式切換欄位、可選時段、即時預覽、送出前確認彈窗 |
| [dim_edit.js](dim_edit.js) | 主檔編輯 | 依角色套用預設權限 |
| [apidocs.js](apidocs.js) / [apidocs.css](apidocs.css) | API 文件 | 載入 Swagger UI |
| [app.css](app.css) | 全部 | 全站樣式與亮 / 暗色主題變數 |

## app.css 的慣例

- **顏色一律用變數**（`--shift-bg`、`--leave-bg` …），亮色與深色各定義一次，元件只引用變數。
- **總覽格子的狀態樣式**：`.s-SHIFT`、`.s-LEAVE`、`.s-OT`、`.s-OFF`、`.s-ACTIVITY`、`.s-PENDING`（虛線框）、`.s-OT_PENDING`；同一天部分上班、部分請假的格子用 `td.split`，分上下兩段。
- **逐日結果標籤**：`.created`、`.updated`、`.skipped`、`.error`。

## 撰寫慣例

- 一個功能一個 `(() => { ... })();` 區塊。元素只在有權限時才出現的區塊，開頭先找元素、找不到就 `return`（例如 `roster.js` 的提交班表、`base.js` 的取消彈窗）；整支只給特定權限用的 JS，則由模板依權限決定要不要載入（例如 `overtime.js` 只在有 `OT_APPLY` 時載入）。
- 伺服器資料從 `data-*` 屬性讀取；要呼叫的 API 網址也由模板放在 `data-*-url`，不在 JS 寫死。
- 顯示使用者輸入或 API 回傳的文字一律用 `textContent`，不用 `innerHTML`。
- 確認彈窗按下送出後立刻停用按鈕，避免連點重複送出；伺服器端仍會再檢查一次。
