# Vantage Roster Situation（排班系統）

以 Flask + SQLite 建置的內部排班系統：提交班表、請假與加班申請 / 主管審核、年度排班總覽，以及班別、員工、假日主檔維護。

- 業務流程、資料表與權限的完整說明：[structure.md](structure.md)
- 所有網址與 API 的說明：啟動後登入（需 `USER_EDIT` 權限），開啟導覽列的「API 文件」（`/apidocs`）

## 目錄

- [系統需求](#系統需求)
- [安裝](#安裝)
- [正式環境](#正式環境)
- [測試環境](#測試環境)
- [自動化測試](#自動化測試)
- [環境變數](#環境變數)
- [專案結構](#專案結構)
- [輔助教材：用 AI 培養自己的思考框架](#輔助教材用-ai-培養自己的思考框架)

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
| `ROSTER_THREADS` | waitress 同時處理的請求數（`12`）；約 100 人使用建議 8–16 |
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
structure.md         設計說明：業務流程、資料表、權限、備份與日誌
```

一個請求的處理順序：`routes/auth.py` 驗證登入 → `routes/` 的對應函式檢查權限 → `forms.py` 解析輸入 → `db.py` 依規則讀寫資料庫 → `views.py` 整理資料 → `templates/` 產生頁面（或回傳 JSON）。

## 輔助教材：用 AI 培養自己的思考框架

維護或擴充這個系統時，很多問題都會拿去問 AI。這一節說明怎麼問，才能讓**自己的判斷力**變強，而不只是拿到一個答案。

### 兩個層次

| 層次 | 做法 | 拿到什麼 |
|---|---|---|
| 第一層：脈絡溝通 | 把背景、目標、限制講清楚再問 | 更好的答案 |
| 第二層：先想再對照 | 自己先想，再拿 AI 的回答檢查自己漏了什麼 | 更好的自己 |

第一層很重要，但只做第一層，提問技巧越好，反而可能越依賴 AI。長期能拉開差距的是第二層：把 AI 當成陪你練習的對象，而不是直接給答案的工具。

### 框架是什麼

框架就是遇到新問題時，腦中自動浮現的幾個「要先確認的問題」。以本系統實際討論過的一個問題為例：

> **問題：** 「要不要把 SQLite 換成 Postgres，好撐住高頻寫入？」
>
> **背後的框架：要不要換技術？先問：**
> 1. 真正的瓶頸是什麼？（100 人使用，換算下來每秒只有個位數寫入，不是 SQLite 撐不住）
> 2. 現有工具的極限在哪？（SQLite 開了 WAL 後，每秒可處理上千筆小型寫入）
> 3. 換掉的代價是什麼？（要改大半個 `db.py`，還會失去「一個檔案就能帶走」的輕便）
> 4. 有沒有更小的改動能先解決？（調整連線等待時間、`synchronous`、waitress 執行緒數）
>
> **結論：** 不換，只調設定。

同一套問題可以直接套用到「要不要換成 FastAPI」「要不要搬上雲端」「要不要加快取」等其他決定。

### 四個練習方法

**1. 先寫下自己的答案，再問 AI**

問之前花 2 分鐘寫下：「我猜答案是 ___，理由是 ___」。拿到 AI 的回答後對照，看哪裡想到了、哪裡漏了。漏掉的部分，就是你的框架缺的那一塊。

**2. 事後抽出可以重複用的問題**

解決一個問題後，問自己：「這次哪個判斷步驟，下次遇到別的問題也用得上？」然後把它記下來。例如：「改技術之前，先確認現有工具的極限在哪裡。」

**3. 請 AI 說明推理過程，而不只是結論**

> 「你判斷不用換資料庫，是先看了哪些因素、依什麼順序判斷的？」

這樣能把它的思考步驟攤開來，讓你檢查、吸收。

**4. 換一個情境，自己套用一次**

學到一個框架後，馬上找另一個問題自己套用，再請 AI 檢查：

> 「我用『要不要換技術』的四個問題分析了『要不要加 Redis 快取』，請指出我哪裡套錯、漏了什麼。」

### 提問範本

第一層的脈絡，加上第二層的「先說出自己的想法」：

```
背景：（系統是什麼、規模多大，例如：排班系統，約 100 人使用）
目標：（真正想解決的問題，而不是想用的做法）
限制：（不能改什麼、偏好什麼，例如：要維持輕便、可整包帶走）
我的想法：（我打算怎麼做，理由是什麼）
請你：先指出我的想法哪裡可能有問題，再給建議；說明你的判斷順序；不確定的地方請直接說。
```

範本中最重要的是「我的想法」和「先指出哪裡可能有問題」：多數人拿 AI 來證實自己的想法，會請它挑戰自己的人才是少數。
