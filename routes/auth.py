"""JWT 登入、登出，以及每次請求的身分驗證。"""
import datetime as dt
import hashlib
import logging

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
    error = None
    notice = "登入已逾時，請重新登入" if request.args.get("expired") else None
    if request.method == "POST":
        emp = db().authenticate(request.form.get("email"), request.form.get("password"))
        if emp is None:
            error, notice = "帳號或密碼錯誤，或帳號尚未開通", None
            _audit_login_failed(request.form.get("email"))
        else:
            audit("登入", "login", user=emp["email"], via="web")
            nxt = request.args.get("next") or ""
            resp = redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("roster.index"))
            resp.set_cookie(config.JWT_COOKIE_NAME, issue_token(emp),
                            max_age=config.JWT_EXPIRE_MINUTES * 60, httponly=True,
                            secure=config.JWT_COOKIE_SECURE, samesite=config.JWT_COOKIE_SAMESITE)
            return resp
    return render_template("login.html", error=error, notice=notice, email=request.form.get("email", ""))


@bp.post("/api/login")
def api_login():
    """{"email": "...", "password": "..."} → {"access_token": "...", "token_type": "Bearer", "expires_in": 1800}"""
    body = request.get_json(silent=True) or {}
    emp = db().authenticate(body.get("email"), body.get("password"))
    if emp is None:
        _audit_login_failed(body.get("email"))
        return jsonify({"ok": False, "error": "帳號或密碼錯誤，或帳號尚未開通"}), 401
    audit("登入", "login", user=emp["email"], via="api")
    return jsonify({"ok": True, "access_token": issue_token(emp), "token_type": "Bearer",
                    "expires_in": config.JWT_EXPIRE_MINUTES * 60})


def _audit_login_failed(login):
    """登入失敗一律記在 _anonymous，附上嘗試的帳號（不記密碼）。"""
    audit("登入失敗", "login_failed", level=logging.WARNING, user=ANONYMOUS_USER, login=(login or "").strip())


@bp.post("/logout")
def logout():
    if g.user is not None:
        audit("登出", "logout")
    resp = redirect(url_for("auth.login"))
    resp.delete_cookie(config.JWT_COOKIE_NAME)
    return resp
