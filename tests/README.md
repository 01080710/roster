# tests/：自動化測試

每個測試使用**全新的暫存資料庫**，不會動到 `roster.db`，也不需要先啟動網站。

```powershell
pip install -r requirements-dev.txt      # 第一次：安裝 pytest
python -m pytest                         # 全部
python -m pytest tests/test_requests.py  # 單一檔案
python -m pytest -k cancel               # 名稱含 cancel 的測試
```

| 檔案 | 涵蓋範圍 |
|---|---|
| [test_roster_rules.py](test_roster_rules.py) | 提交班表的規則（休息日、國定假日、覆蓋權限、兩班間休息時數）、預覽與全有或全無、總覽的期間與顯示、員工資料 join、舊資料庫升級、Agent 班別限制 |
| [test_requests.py](test_requests.py) | 請假與加班的申請、審核、撤回、取消（含影響預覽與必填原因）、單號產生、個資可見範圍 |
| [test_web_security.py](test_web_security.py) | 登入後跳轉、CSRF、登入失敗鎖定、一次性訊息、他人備註隱藏、CSP、API 文件權限 |
| [conftest.py](conftest.py) | 共用 fixture 與工具 |

## conftest.py 提供的東西

- **初始員工**：`EMP0001`（Admin，最高主管）、`EMP0002`（AM）、`EMP0003`（Agent），後兩位的主管都是 `EMP0001`；三人的密碼都是常數 `PASSWORD`。
- **fixture**：`db_path`（建好的暫存資料庫路徑）、`rdb`（直接呼叫 `RosterDB`）、`client`（Flask 測試用瀏覽器）。
- **工具**：`login(client, emp_id)` 用網頁表單登入；`bearer(client, emp_id)` 取得 API 用的 `Authorization` header；`set_csrf(client)` 與常數 `CSRF` 用於送出 POST 表單。

## 撰寫慣例

- **每項改動附一個回歸測試**，函式名稱直接寫出規則，例如 `test_submit_range_writes_nothing_when_any_day_fails`。
- **日期用 2026 年 11 月**：2026-11-02 是週一，11-07、11-08 是週末，方便測試略過非工作日。
- **規則測 `rdb`、權限與畫面測 `client`**：業務規則直接呼叫 `RosterDB`；權限、CSRF、頁面是否渲染出元素用 `client`。
- **會改動資料的功能要測三件事**：預覽不寫入、成功時寫入、失敗時一筆都不寫。
- 會寫入備份資料夾的測試，用 `monkeypatch` 把 `BACKUP_DIR` 改到 `tmp_path`，不要寫進專案的 `backups/`。
