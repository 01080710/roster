"""JWT 登入、登出，以及每次請求的身分驗證。"""
import datetime as dt
import hashlib
import logging
import math
import threading
import time
from urllib.parse import urlsplit

import jwt
from flask import Blueprint, g, jsonify, redirect, render_template, request, url_for

import config
from db import parse_permissions

from .common import ANONYMOUS_USER, audit, can, can_leave, can_overtime, db

bp = Blueprint("auth", __name__)


def _password_fingerprint(emp):
    """放進 token 的密碼指紋：密碼一改，舊 token 立即失效。"""
    return hashlib.sha256((emp["password_hash"] or "").encode()).hexdigest()[:16]


def issue_token(emp):
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": emp["employee_id"],
        "iat": now,
        "exp": now + dt.timedelta(minutes=config.JWT_EXPIRE_MINUTES),
        "pwd": _password_fingerprint(emp),
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def _request_token():
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(config.JWT_COOKIE_NAME)


@bp.before_app_request
def load_user():
    """每次請求驗證 JWT，並重新讀取員工資料；離職、密碼變更或清除時立即失效。"""
    g.user, g.perms, g.token_exp, g.auth_error = None, set(), None, None
    token = _request_token()
    if not token:
        return
    try:
        claims = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM],
                            options={"require": ["sub", "exp", "iat"]})
    except jwt.ExpiredSignatureError:
        g.auth_error = "expired"
        return
    except jwt.InvalidTokenError:
        g.auth_error = "invalid"
        return
    emp = db().get_employee(claims["sub"])
    if db().can_login(emp) and claims.get("pwd") == _password_fingerprint(emp):
        g.user, g.perms, g.token_exp = emp, set(parse_permissions(emp["permission"])), claims["exp"]
    else:
        g.auth_error = "invalid"


@bp.after_app_request
def clear_bad_cookie(response):
    """cookie 裡的 token 過期或無效時順便清掉。"""
    if g.get("auth_error") and request.cookies.get(config.JWT_COOKIE_NAME):
        response.delete_cookie(config.JWT_COOKIE_NAME)
    return response


@bp.app_context_processor
def inject_nav():
    # 班別 / 員工 / 假日主檔需要 USER_EDIT，Agent（VIEW + CREATE）看不到
    dims = [(k, m["label"]) for k, m in config.DIM_TABLES.items()] if can("USER_EDIT") else []
    user = g.get("user")
    pending = db().pending_leave_count(user["employee_id"]) if user and can("LEAVE_APPROVE") else 0
    pending_ot = db().pending_overtime_count(user["employee_id"]) if user and can("OT_APPROVE") else 0
    return {"nav_dims": dims, "current_user": user, "token_exp": g.get("token_exp"), "can": can,
            "can_leave": user is not None and can_leave(), "nav_pending_leave": pending,
            "can_overtime": user is not None and can_overtime(), "nav_pending_overtime": pending_ot}


@bp.app_errorhandler(403)
def forbidden(_):
    return render_template("forbidden.html"), 403


@bp.route("/login", methods=["GET", "POST"])
def login():
    """登入頁
    ---
    get:
      summary: 顯示登入頁
      parameters:
        - {name: next, in: query, schema: {type: string}, description: 登入成功後要回到的站內網址，例如 /leave}
        - {name: expired, in: query, schema: {type: string}, description: 有值時顯示「登入已逾時」}
      responses:
        200: {description: 登入頁（HTML）}
    post:
      summary: 送出帳號密碼登入（網頁）
      description: 成功時把 JWT 存進 HttpOnly cookie，再導向 next 或排班總覽。
      parameters:
        - {name: next, in: query, schema: {type: string}, description: 登入成功後要回到的站內網址}
      requestBody:
        content:
          application/x-www-form-urlencoded:
            schema:
              type: object
              required: [email, password]
              properties:
                email: {type: string, example: you@example.com}
                password: {type: string, format: password}
      responses:
        302: {description: 登入成功：設定 cookie 並導向 next 或排班總覽}
        200: {description: 帳號或密碼錯誤：重新顯示登入頁與錯誤訊息}
    """
    error = None
    notice = "登入已逾時，請重新登入" if request.args.get("expired") else None
    if request.method == "POST":
        emp, error, _ = _try_login(request.form.get("email"), request.form.get("password"))
        if emp is None:
            notice = None
        else:
            audit("登入", "login", user=emp["email"], via="web")
            resp = redirect(_safe_next(request.args.get("next")))
            resp.set_cookie(config.JWT_COOKIE_NAME, issue_token(emp),
                            max_age=config.JWT_EXPIRE_MINUTES * 60, httponly=True,
                            secure=config.JWT_COOKIE_SECURE, samesite=config.JWT_COOKIE_SAMESITE)
            return resp
    return render_template("login.html", error=error, notice=notice, email=request.form.get("email", ""))


@bp.post("/api/login")
def api_login():
    """取得 token（外部程式用）
    之後每次呼叫帶 `Authorization: Bearer <access_token>`；token 到期後重新呼叫一次。
    ---
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [email, password]
            properties:
              email: {type: string, example: you@example.com}
              password: {type: string, format: password}
    responses:
      200:
        description: 登入成功
        content:
          application/json:
            example: {ok: true, access_token: eyJhbGciOiJIUzI1NiIs..., token_type: Bearer, expires_in: 1800}
      401:
        description: 帳號或密碼錯誤，或帳號尚未開通（沒有密碼、已離職）
        content:
          application/json:
            example: {ok: false, error: 帳號或密碼錯誤，或帳號尚未開通}
      429:
        description: 同一帳號短時間內失敗太多次，暫時鎖定（次數與時間見 config.LOGIN_*）
        content:
          application/json:
            example: {ok: false, error: 登入失敗次數過多，請 15 分鐘後再試}
    """
    body = request.get_json(silent=True) or {}
    emp, error, status = _try_login(body.get("email"), body.get("password"))
    if emp is None:
        return jsonify({"ok": False, "error": error}), status
    audit("登入", "login", user=emp["email"], via="api")
    return jsonify({"ok": True, "access_token": issue_token(emp), "token_type": "Bearer",
                    "expires_in": config.JWT_EXPIRE_MINUTES * 60})


def _safe_next(nxt):
    """登入後只導回站內路徑；擋掉 //evil.com、/\\evil.com、https://evil.com 這類會跳到外部網站的網址。"""
    if nxt and nxt.startswith("/") and "\\" not in nxt and not any(c < " " for c in nxt):
        parts = urlsplit(nxt)
        if not parts.scheme and not parts.netloc:
            return nxt
    return url_for("roster.index")


# 登入失敗次數限制：同一帳號 LOGIN_WINDOW_MINUTES 內失敗 LOGIN_MAX_FAILURES 次，鎖 LOGIN_LOCK_MINUTES。
# 記在記憶體（waitress 是單一行程多執行緒，所以要加鎖），重開網站會歸零。
_failures = {}          # 帳號 → 最近幾次失敗的時間
_locked_until = {}      # 帳號 → 解鎖時間
_limit_lock = threading.Lock()


def _locked_minutes(key):
    """還要鎖幾分鐘；沒有鎖定回傳 0。"""
    with _limit_lock:
        left = _locked_until.get(key, 0) - time.monotonic()
        if left <= 0:
            _locked_until.pop(key, None)
            return 0
        return math.ceil(left / 60)


def _record_failure(key):
    """記一次失敗；達到上限時鎖定並回傳 True。"""
    now, window = time.monotonic(), config.LOGIN_WINDOW_MINUTES * 60
    with _limit_lock:
        for k in [k for k, ts in _failures.items() if now - ts[-1] >= window]:   # 清掉過期的，避免越存越多
            del _failures[k]
        recent = [t for t in _failures.get(key, []) if now - t < window] + [now]
        if len(recent) >= config.LOGIN_MAX_FAILURES:
            _locked_until[key] = now + config.LOGIN_LOCK_MINUTES * 60
            _failures.pop(key, None)
            return True
        _failures[key] = recent
        return False


def _try_login(login, password):
    """網頁與 API 共用：驗證帳密並套用失敗次數限制。回傳 (員工, 錯誤訊息, HTTP 狀態碼)。
    鎖定期間不檢查密碼，猜對也進不去。"""
    key = (login or "").strip().lower()
    wait = _locked_minutes(key)
    if wait:
        audit("登入被拒：帳號暫時鎖定", "login_locked", level=logging.WARNING, user=ANONYMOUS_USER, login=key)
        return None, f"登入失敗次數過多，請 {wait} 分鐘後再試", 429
    emp = db().authenticate(login, password)
    if emp is None:
        _audit_login_failed(login)
        if _record_failure(key):
            audit("登入失敗次數過多，帳號暫時鎖定", "login_lock", level=logging.WARNING, user=ANONYMOUS_USER,
                  login=key, minutes=config.LOGIN_LOCK_MINUTES)
        return None, "帳號或密碼錯誤，或帳號尚未開通", 401
    with _limit_lock:
        _failures.pop(key, None)
    return emp, None, 200


def _audit_login_failed(login):
    """登入失敗一律記在 _anonymous，附上嘗試的帳號（不記密碼）。"""
    audit("登入失敗", "login_failed", level=logging.WARNING, user=ANONYMOUS_USER, login=(login or "").strip())


@bp.post("/logout")
def logout():
    """登出
    清除 token cookie。JWT 本身沒有存在伺服器，所以外部程式拿到的 token 在到期前仍然有效。
    ---
    responses:
      302: {description: 清除 cookie 並導向登入頁}
    """
    if g.user is not None:
        audit("登出", "logout")
    resp = redirect(url_for("auth.login"))
    resp.delete_cookie(config.JWT_COOKIE_NAME)
    return resp
