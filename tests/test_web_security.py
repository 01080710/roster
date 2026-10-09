"""網頁與 API 的安全防護：登入跳轉、CSRF、登入次數限制、一次性訊息、個資、CSP、API 文件權限。"""
import datetime as dt
from urllib.parse import quote, urlsplit

import pytest

import config
from conftest import CSRF, EMAIL, bearer, login, set_csrf

D = dt.date


# ---------------- 登入後跳轉 ----------------
@pytest.mark.parametrize("nxt, expected", [
    ("/leave", "/leave"),
    ("//evil.com", "/"),
    ("/\\evil.com", "/"),
    ("https://evil.com/", "/"),
    ("/\t/evil.com", "/"),
])
def test_login_next_only_allows_site_paths(client, nxt, expected):
    r = login(client, "EMP0001", query=f"?next={quote(nxt)}")
    assert r.status_code == 302
    loc = urlsplit(r.headers["Location"])
    assert loc.netloc in ("", "localhost") and loc.path == expected


# ---------------- CSRF ----------------
def test_form_post_without_csrf_token_is_rejected(client):
    login(client, "EMP0003")
    form = {"shift_code": "AL_FD", "start_date": "2026-11-10"}
    assert client.post("/leave", data=form).status_code == 400
    assert client.post("/leave", data=form | {"csrf_token": "wrong"}).status_code == 400
    assert client.post("/leave", data=form | {"csrf_token": CSRF}).status_code == 302


def test_cookie_api_post_needs_csrf_header_but_bearer_does_not(client):
    body = {"start_date": "2026-11-07", "shift_code": "OT_FD"}
    login(client, "EMP0003")
    assert client.post("/api/overtime", json=body).status_code == 403
    assert client.post("/api/overtime", json=body, headers={"X-CSRF-Token": CSRF}).status_code == 200
    client.delete_cookie("access_token")
    r = client.post("/api/overtime", json=body | {"start_date": "2026-11-14"}, headers=bearer(client, "EMP0003"))
    assert r.status_code == 200


def test_login_page_itself_requires_csrf(client):
    set_csrf(client)
    r = client.post("/login", data={"email": EMAIL["EMP0001"], "password": "password123"})
    assert r.status_code == 400


# ---------------- 登入失敗次數限制 ----------------
def test_account_locks_after_repeated_failures(client):
    for _ in range(config.LOGIN_MAX_FAILURES):
        assert login(client, "EMP0001", password="wrong").status_code == 200       # 留在登入頁
    r = login(client, "EMP0001")                                                    # 密碼正確也進不去
    assert r.status_code == 200 and "失敗次數過多" in r.get_data(as_text=True)
    r = client.post("/api/login", json={"email": EMAIL["EMP0001"], "password": "password123"})
    assert r.status_code == 429
    assert login(client, "EMP0002").status_code == 302                            # 其他帳號不受影響


def test_success_resets_failure_count(client):
    for _ in range(config.LOGIN_MAX_FAILURES - 1):
        login(client, "EMP0001", password="wrong")
    assert login(client, "EMP0001").status_code == 302
    for _ in range(config.LOGIN_MAX_FAILURES - 1):
        login(client, "EMP0001", password="wrong")
    assert login(client, "EMP0001").status_code == 302


# ---------------- 一次性訊息 ----------------
def test_message_cannot_be_injected_via_url(client):
    login(client, "EMP0003")
    assert "請至" not in client.get("/leave?msg=請至 evil.com 重新驗證").get_data(as_text=True)


def test_message_shows_once_after_redirect(client):
    login(client, "EMP0003")
    client.post("/leave", data={"shift_code": "AL_FD", "start_date": "2026-11-10", "csrf_token": CSRF})
    assert "已送出申請單" in client.get("/leave").get_data(as_text=True)
    assert "已送出申請單" not in client.get("/leave").get_data(as_text=True)


# ---------------- 請假原因（個資） ----------------
def test_detail_hides_other_peoples_reasons(client, rdb):
    rid = rdb.create_leave_request("EMP0003", "AL_FD", D(2026, 11, 10), D(2026, 11, 10), "看醫生")
    rdb.approve_leave_request(rid, "EMP0001")

    def remarks_seen_by(emp_id):
        d = client.get("/api/roster/detail?kind=leave&year=2026&month=11", headers=bearer(client, emp_id)).get_json()
        return [r["cells"][-1] for r in d["rows"]]

    assert any("看醫生" in c for c in remarks_seen_by("EMP0003"))       # 本人
    assert any("看醫生" in c for c in remarks_seen_by("EMP0001"))       # 主管
    assert not any("看醫生" in c for c in remarks_seen_by("EMP0002"))   # 其他人


# ---------------- CSP 與 API 文件 ----------------
def test_pages_send_content_security_policy(client):
    r = client.get("/login")
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]


def test_apidocs_needs_user_edit_and_spec_builds(client):
    assert client.get("/apidocs").status_code == 302                     # 未登入 → 登入頁
    login(client, "EMP0003")
    assert client.get("/apidocs").status_code == 403                     # Agent 沒有 USER_EDIT
    login(client, "EMP0001")
    spec = client.get("/apidocs/openapi.json").get_json()
    assert spec["openapi"].startswith("3.") and "/api/leave/preview" in spec["paths"]
