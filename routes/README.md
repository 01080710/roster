# routes/：網址與 API

依業務拆成 Flask Blueprint，在 [routes/__init__.py](__init__.py) 註冊。每支函式只負責「檢查權限 → 解析輸入 → 呼叫 `db.py` → 回傳頁面或 JSON」，業務規則一律放在 [db.py](../db.py)。

| 檔案 | 負責 | 主要網址 |
|---|---|---|
| [auth.py](auth.py) | 登入、登出、身分驗證（JWT） | `/login`、`/logout`、`POST /api/login` |
| [roster.py](roster.py) | 排班總覽、提交班表、匯出 | `/`、`/export/roster`、`/api/roster`、`/api/roster/preview`、`/api/roster/detail` |
| [leave.py](leave.py) | 請假申請、審核、取消 | `/leave`、`/leave/<id>/decide`、`/leave/<id>/cancel`、`/api/leave/preview`、`/api/leave/<id>/cancel-preview` |
| [overtime.py](overtime.py) | 加班申請、審核、取消 | `/overtime`、`/overtime/<id>/decide`、`/overtime/<id>/cancel`、`/api/overtime`、`/api/overtime/preview`、`/api/overtime/slots`、`/api/overtime/<id>/cancel-preview` |
| [dim.py](dim.py) | 班別 / 員工 / 假日主檔 | `/dim/<kind>`、`/dim/<kind>/edit`、`/dim/<kind>/delete`、`/dim/<kind>/export` |
| [apidocs.py](apidocs.py) | API 文件（Swagger UI） | `/apidocs`、`/apidocs/openapi.json` |
| [common.py](common.py) | 共用工具，不註冊網址 | — |

完整的參數與回傳範例：登入後開啟導覽列的「API 文件」（需 `USER_EDIT`）。

## common.py 的共用工具

| 函式 | 用途 |
|---|---|
| `require(*perms)` | 裝飾器：未登入時網頁導向登入頁、API 回 401；缺權限回 403 |
| `can(*perms)` | 目前使用者是否有這些權限（模板也能用） |
| `db()` | 取得這次請求的 `RosterDB` 連線，請求結束自動關閉 |
| `check_own_employee`、`check_leave_shift`、`check_agent_shift`、`shift_allowed` | 提交班表的共用檢查：本人限制、請假代碼、Agent 只能選預設班別 |
| `csrf_token()`、`check_csrf()` | CSRF 保護；POST 表單與用 cookie 呼叫的 API 都會檢查 |
| `redirect_msg(endpoint, msg)` | 導回頁面並顯示一次性訊息（存在簽章 session，不能從網址帶入） |
| `audit(message, action, **fields)` | 寫一筆行為日誌（`behavior.log`） |
| `csv_download(filename, columns, rows)` | 匯出 CSV（UTF-8 BOM、防公式注入） |

## 撰寫慣例

- **權限**：每支函式都加 `@require(...)`；需要「只能操作自己的」時，在函式內再檢查。前端隱藏按鈕不算保護，伺服器端一定要擋。
- **錯誤**：業務規則不符時 `db.py` 丟 `ValueError`，路由接住後：頁面用 `redirect_msg(..., error=True)`，API 回 `{"ok": false, "error": ...}` 與 400。
- **先預覽再寫入**：會改動資料的操作提供對應的 `GET .../preview`，與正式寫入呼叫同一段 `db.py` 程式（試跑後 rollback），規則只有一套。
- **API 文件**：函式說明文字的第一行是標題，`---` 之後用 YAML 寫參數與回傳範例，`/apidocs` 會自動產生。YAML 的 `{}` 有特殊意義，說明文字裡不要寫 `{request_id}` 這種寫法。
- **日誌**：關鍵動作用 `audit()` 記錄；不記密碼、token、請假 / 加班原因（只記字數）。
