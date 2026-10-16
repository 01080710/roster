# templates/：頁面模板（Jinja）

所有頁面繼承 [base.html](base.html)（導覽列、主題切換、登入有效時間）。頁面的互動行為寫在 [static/](../static/) 對應的 JS。

| 檔案 | 頁面 | 對應的 JS |
|---|---|---|
| [base.html](base.html) | 共用版面 | `theme.js`、`base.js` |
| [login.html](login.html) | 登入 | — |
| [roster.html](roster.html) | 排班總覽、提交班表（含預覽彈窗）、查詢與修改、逐日明細 | `roster.js` |
| [leave.html](leave.html) | 請假：月曆、待審核、我的請假、審核紀錄 | `leave.js` |
| [overtime.html](overtime.html) | 加班：待審核、我的加班（含確認彈窗）、審核紀錄 | `overtime.js` |
| [dim_list.html](dim_list.html) / [dim_edit.html](dim_edit.html) | 班別 / 員工 / 假日主檔的列表與編輯 | `dim_edit.js` |
| [apidocs.html](apidocs.html) | API 文件 | `apidocs.js` |
| [forbidden.html](forbidden.html) | 沒有權限（403） | — |

## 共用片段（`_` 開頭）

| 檔案 | 內容 | 用法 |
|---|---|---|
| [_messages.html](_messages.html) | 一次性訊息（`redirect_msg()` 留下的） | `{% from "_messages.html" import flashes %}{{ flashes() }}` |
| [_cancel_dialog.html](_cancel_dialog.html) | 主管取消已核准申請：影響預覽 + 必填原因 | `cancel_button(q, 取消的 endpoint, 預覽的 endpoint)`、`cancel_dialog(說明文字)` |

## 撰寫規則（CSP 限制）

頁面有 Content-Security-Policy，**模板裡不能直接寫程式或樣式**，否則瀏覽器會擋掉：

- 不寫 `<script>…</script>`、`<style>`、`style="…"`、`onclick="…"`；程式放 `static/*.js`，樣式放 `static/app.css`。
- 伺服器的資料用 `data-*` 屬性交給 JS，例如 `data-preview-url="{{ url_for(...) }}"`。
- 每個 POST 表單都要放 `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`。
- 送出前確認用 `<form data-confirm="訊息">`；下拉選了就送出用 `<select data-autosubmit>`；彈窗的關閉按鈕加 `data-close`。
- 會改動資料的重要操作（提交班表、送出加班、取消已核准的單）用頁面內的彈窗確認，不用瀏覽器的 `confirm()`。
