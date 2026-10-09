# Vantage Roster Situation（排班系統）

以 Flask + SQLite 建置的內部排班系統：提交班表、請假與加班申請 / 主管審核、年度排班總覽，以及班別、員工、假日主檔維護。

- 業務流程、資料表與權限的完整說明：[db_structure.md](db_structure.md)
- 所有網址與 API 的說明：啟動後登入（需 `USER_EDIT` 權限），開啟導覽列的「API 文件」（`/apidocs`）

## 目錄

- [系統需求](#系統需求)
- [安裝](#安裝)
- [正式環境](#正式環境)
- [測試環境](#測試環境)
- [自動化測試](#自動化測試)
- [環境變數](#環境變數)
- [專案結構](#專案結構)

## 系統需求

- Python 3.12 以上
- Windows、macOS 或 Linux（以下指令以 Windows PowerShell 為主，另附 macOS / Linux 寫法）
- 資料庫檔案 `roster.db` 必須放在**伺服器本機磁碟**：SQLite 的 WAL 模式不支援網路磁碟機

## 安裝

在專案資料夾執行一次：

```powershell
# Windows PowerShell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install tzdata                 # Windows 才需要（時區資料）
```

```bash
# macOS / Linux
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

之後每次開新的終端機，都要先啟用虛擬環境（`.venv\Scripts\Activate.ps1` 或 `source .venv/bin/activate`），再執行下面的指令。

## 正式環境

正式環境用 **waitress** 啟動（`ROSTER_DEBUG` 沒設或設為 `0` 時的預設值）。

### 1. 第一次部署

```powershell
# 1. 設定固定的密鑰（用來簽署登入 token；之後不要再改，改了所有人都要重新登入）
python -c "import secrets; print(secrets.token_hex(32))"      # 產生一組，複製下來
setx ROSTER_SECRET_KEY "<剛剛產生的密鑰>"                      # 永久設定；需重開終端機才生效

# 2. 替要登入的員工設定密碼（帳號為員工 email；沒有密碼的員工不能登入）
#    第一次執行時會自動建立 roster.db，並寫入班別、假日與員工的初始資料
python main.py set-password peter.chang@hytechc.com
```

沒有設定 `ROSTER_SECRET_KEY` 時，系統會在專案資料夾自動產生 `.secret_key` 檔並沿用。這個檔案不能刪除，也不可放進版本控制（已在 `.gitignore` 排除）。

### 2. 啟動

```powershell
# Windows PowerShell
python main.py
```

```bash
# macOS / Linux
python main.py
```

預設只接受本機連線：<http://127.0.0.1:5000>。要讓其他電腦連線：

```powershell
$env:ROSTER_HOST = "0.0.0.0"       # 接受所有網路介面的連線
$env:ROSTER_PORT = "8000"          # 需要時換 port
python main.py
```

> **對外開放時請走 HTTPS**：waitress 只提供 HTTP。請在前面加一層提供 HTTPS 的反向代理（例如 IIS、nginx），並設定 `$env:ROSTER_COOKIE_SECURE = "true"`，讓登入 cookie 只走加密連線。

啟動時會自動完成這些事：升級舊版資料庫、備份一次、清理過期日誌，之後每天凌晨 3 點再備份與清理一次。

### 3. 日常維運指令

| 用途 | 指令 |
|---|---|
| 設定 / 重設員工密碼 | `python main.py set-password <email 或 employee_id>` |
| 手動備份資料庫 | `python main.py backup`（存到 `backups/roster_YYYYMMDD_HHMMSS.db`） |
| 還原備份 | 停止網站 → 把備份檔複製回專案資料夾並改名為 `roster.db`（同時刪除舊的 `roster.db-wal`、`roster.db-shm`）→ 啟動 |
| 查看日誌 | `logs/YYYY-MM-DD/<使用者 email>/behavior.log`（操作紀錄）、`debug.log`（系統執行） |

### 4. 更新程式版本

```powershell
# 先停止網站（Ctrl+C）
python main.py backup              # 更新前先備份
git pull
pip install -r requirements.txt    # 套件可能有新增或升級
python -m pytest                   # 建議：確認新版本的測試全部通過（需先安裝 requirements-dev.txt）
python main.py                     # 重新啟動；資料庫如需升級會自動進行
```

> `roster.db` 旁邊的 `roster.db-wal`、`roster.db-shm` 是 SQLite WAL 模式的正常檔案，網站執行中**不要刪除**。

## 測試環境

用來開發或驗證新功能。使用 Flask 開發伺服器（改程式後自動重新載入，錯誤時顯示細節），並與正式資料**完全分開**：獨立的資料庫、日誌資料夾與 port。

> Flask 開發伺服器不安全，**不可對外開放**，也不要指向正式的 `roster.db`。

```powershell
# Windows PowerShell（只對目前這個終端機有效）
$env:ROSTER_DEBUG   = "1"                    # 開發模式
$env:ROSTER_DB_PATH = "$PWD\roster_test.db"  # 測試用資料庫，第一次啟動會自動建立
$env:ROSTER_LOG_DIR = "$PWD\test_logs"       # 測試日誌另外存放
$env:ROSTER_STAGE   = "test"                 # 日誌標記為 test
$env:ROSTER_PORT    = "5001"                 # 避開正式環境的 5000
$env:ROSTER_BACKUP  = "false"                # 測試資料不需要每日備份
python main.py set-password peter.chang@hytechc.com   # 設定測試帳號的密碼（寫進 roster_test.db）
python main.py
```

```bash
# macOS / Linux
export ROSTER_DEBUG=1 ROSTER_DB_PATH="$PWD/roster_test.db" ROSTER_LOG_DIR="$PWD/test_logs" \
       ROSTER_STAGE=test ROSTER_PORT=5001 ROSTER_BACKUP=false
python main.py set-password peter.chang@hytechc.com
python main.py
```

開啟 <http://127.0.0.1:5001>。

想用正式資料的複本來測試，可以拿最新的備份：先把 `backups/` 裡最新的檔案複製成 `roster_test.db`，再啟動。

回到正式環境前，關掉這個終端機，或清除這些設定：

```powershell
Remove-Item Env:ROSTER_DEBUG, Env:ROSTER_DB_PATH, Env:ROSTER_LOG_DIR, Env:ROSTER_STAGE, Env:ROSTER_PORT, Env:ROSTER_BACKUP
```

## 自動化測試

測試放在 [tests/](tests/)，涵蓋班表規則、請假 / 加班的申請與審核流程，以及網頁安全防護（CSRF、登入次數限制、登入後跳轉、個資遮蔽等）。每個測試都使用全新的暫存資料庫，**不會動到 `roster.db`**，也不需要先啟動網站。

```powershell
pip install -r requirements-dev.txt          # 第一次：安裝 pytest

python -m pytest                             # 執行全部測試
python -m pytest tests/test_requests.py      # 只跑某個檔案
python -m pytest -k csrf                     # 只跑名稱含 csrf 的測試
python -m pytest -x                          # 遇到第一個失敗就停止
```

修改 `db.py` 的規則或 `routes/` 之後，請先執行一次，確認沒有改壞既有功能。

## 環境變數

都可以不設，括號內是預設值。

| 變數 | 用途 |
|---|---|
| `ROSTER_SECRET_KEY` | 簽署登入 token 與 session 的密鑰（未設定時自動產生 `.secret_key` 檔）。**正式環境建議設定** |
| `ROSTER_HOST` | 監聽位址（`127.0.0.1`，只接受本機）；`0.0.0.0` 為接受所有連線 |
| `ROSTER_PORT` | port（`5000`） |
| `ROSTER_DEBUG` | `1` 為開發模式，使用 Flask 開發伺服器（`0`，使用 waitress） |
| `ROSTER_DB_PATH` | 資料庫檔案位置（專案資料夾的 `roster.db`） |
| `ROSTER_COOKIE_SECURE` | `true` 時登入 cookie 只走 HTTPS（`false`）；走 HTTPS 時請打開 |
| `ROSTER_BACKUP` | 是否自動備份（`true`） |
| `ROSTER_BACKUP_DIR` | 備份資料夾（`backups/`） |
| `ROSTER_LOG_DIR` | 日誌資料夾（`logs/`） |
| `ROSTER_STAGE` | 寫在每筆日誌上的環境標記（`local`），例如 `prod`、`test` |

排班規則、登入有效時間、登入失敗鎖定次數、備份保留天數等設定，在 [config.py](config.py) 直接修改。

## 專案結構

```
main.py              啟動網站、每日備份排程、指令列（set-password、backup）
config.py            可調整的設定與環境變數
db.py                資料表定義、初始資料、資料庫升級、所有業務規則（RosterDB）
forms.py             表單 / JSON 輸入解析
views.py             畫面與匯出用的資料轉換
logger.py            JSON 日誌
routes/              網址與 API（依業務分：auth、roster、leave、overtime、dim、apidocs；共用的在 common）
templates/           頁面模板（Jinja）
static/              CSS 與各頁 JS
tests/               自動化測試（pytest）
requirements.txt     執行需要的套件
requirements-dev.txt 開發與測試需要的套件
db_structure.md      設計說明：業務流程、資料表、權限、備份與日誌
```

一個請求的處理順序：`routes/auth.py` 驗證登入 → `routes/` 的對應函式檢查權限 → `forms.py` 解析輸入 → `db.py` 依規則讀寫資料庫 → `views.py` 整理資料 → `templates/` 產生頁面（或回傳 JSON）。
