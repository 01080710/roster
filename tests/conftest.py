"""測試共用設定：每個測試一個全新的暫存資料庫（含初始的班別、假日、員工），不會碰到 roster.db。

初始員工：EMP0001 Peter（Admin，最高主管）、EMP0002 Laura（AM）、EMP0003 Joanne（Agent），
後兩位的主管（parent_id）都是 EMP0001。測試裡三人的密碼都設成 PASSWORD。
"""
import os
import sys
import tempfile

# config 在 import 時就讀環境變數，所以要在 import 專案程式之前設定
_TMP = tempfile.mkdtemp(prefix="roster-test-")
os.environ.update(ROSTER_DB_PATH=os.path.join(_TMP, "unused.db"), ROSTER_LOG_DIR=os.path.join(_TMP, "logs"),
                  ROSTER_SECRET_KEY="test-secret", ROSTER_BACKUP="0", ROSTER_DEBUG="0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import main  # noqa: E402
from db import RosterDB  # noqa: E402
from routes import auth  # noqa: E402

PASSWORD = "password123"
EMAIL = {"EMP0001": "peter.chang@hytechc.com", "EMP0002": "laura.lim@hytechc.com",
         "EMP0003": "joanne.loy@hytechc.com"}
CSRF = "test-csrf-token"


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "roster.db")
    with RosterDB(path) as rdb:
        rdb.init_db()
        for emp_id in EMAIL:
            rdb.set_password(emp_id, PASSWORD)
    return path


@pytest.fixture
def rdb(db_path):
    with RosterDB(db_path) as conn:
        yield conn


@pytest.fixture
def client(db_path):
    main.app.config.update(TESTING=True, DB_PATH=db_path)
    auth._failures.clear()          # 登入失敗次數存在記憶體，每個測試重新開始
    auth._locked_until.clear()
    with main.app.test_client() as c:
        yield c


def set_csrf(client):
    """把已知的 CSRF token 放進 session，之後 POST 帶 CSRF 即可。"""
    with client.session_transaction() as s:
        s["csrf"] = CSRF


def login(client, emp_id, password=PASSWORD, query=""):
    """用網頁表單登入；成功後 client 會帶著登入 cookie。"""
    set_csrf(client)
    return client.post(f"/login{query}", data={"email": EMAIL[emp_id], "password": password, "csrf_token": CSRF})


def bearer(client, emp_id):
    """用 /api/login 取得 token，回傳 Authorization header。"""
    r = client.post("/api/login", json={"email": EMAIL[emp_id], "password": PASSWORD})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}
