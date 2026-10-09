"""各 router 共用：資料庫連線、權限檢查、CSV 下載、日誌。"""
import csv
import functools
import io
import logging
import time

from flask import (Response, abort, current_app, g, got_request_exception, has_request_context, jsonify,
                   redirect, request, url_for)

import config
import views
from db import RosterDB
from logger import SYSTEM_USER, get_logger

ANONYMOUS_USER = "_anonymous"


class RequestContextFilter(logging.Filter):
    """自動補上是誰（登入者 email / _anonymous / _system）與請求資訊，決定寫到哪個使用者資料夾。"""

    def filter(self, record):
        if not has_request_context():
            record.__dict__.setdefault("user", SYSTEM_USER)
            return True
        user = g.get("user")
        record.__dict__.setdefault("user", user["email"] if user else ANONYMOUS_USER)
        record.__dict__.setdefault("method", request.method)
        record.__dict__.setdefault("path", request.path)
        record.__dict__.setdefault("ip", request.remote_addr)
        return True


log = get_logger(service="roster", logger_name="roster", stage=config.LOG_STAGE, log_dir=config.LOG_DIR)
if not any(isinstance(f, RequestContextFilter) for f in log.logger.filters):
    log.logger.addFilter(RequestContextFilter())


def audit(message, action, level=logging.INFO, **fields):
    """使用者行為：寫到 behavior.log。"""
    log.log(level, message, extra={"channel": "behavior", "action": action, **fields})


def init_logging(app):
    """debug.log：每個請求的狀態碼與耗時，以及未處理的例外（含 traceback）。"""
    @app.before_request
    def _start_timer():
        g.request_started = time.perf_counter()

    @app.after_request
    def _log_request(response):
        started = g.get("request_started")
        ms = round((time.perf_counter() - started) * 1000, 1) if started else None
        log.info("request", extra={"status_code": response.status_code, "duration_ms": ms})
        return response

    def _log_exception(sender, exception, **_):
        log.error("未處理的例外", exc_info=exception)

    got_request_exception.connect(_log_exception, app, weak=False)


def db() -> RosterDB:
    if "db" not in g:
        g.db = RosterDB(current_app.config.get("DB_PATH", config.DB_PATH))
    return g.db


def close_db(_):
    rdb = g.pop("db", None)
    if rdb is not None:
        rdb.close()


def can(*perms):
    return all(p in g.perms for p in perms)


def self_only():
    """沒有 USER_EDIT 的帳號（Agent）只能提交自己的排班。"""
    return not can("USER_EDIT")


def check_own_employee(employee_id):
    if self_only() and employee_id != g.user["employee_id"]:
        raise ValueError("只能提交自己的排班")


def check_leave_shift(shift_code):
    """請假要走申請流程；只有能審核請假的人可以直接在班表填請假代碼。"""
    sh = db().get_shift(shift_code)
    if sh is not None and sh["status_group"] == "Leave" and not can("LEAVE_APPROVE"):
        raise ValueError("請假請到「請假」頁面送出申請")


def can_leave():
    return can("LEAVE_APPLY") or can("LEAVE_APPROVE")


def can_overtime():
    return can("OT_APPLY") or can("OT_APPROVE")


def require(*perms):
    """未登入或 token 過期：網頁導向登入頁，API 回 401；缺權限回 403。"""
    def deco(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            if g.user is None:
                expired = g.auth_error == "expired"
                if request.path.startswith("/api/"):
                    msg = "登入已逾時，請重新取得 token" if expired else "請先登入"
                    return jsonify({"ok": False, "error": msg}), 401
                return redirect(url_for("auth.login", next=request.full_path, expired=1 if expired else None))
            if not can(*perms):
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return deco


def result_counts(results):
    """逐日結果統計：新增 / 更新 / 略過 / 失敗各幾天。"""
    return {k: sum(1 for r in results if r["action"] == k) for k in ("created", "updated", "skipped", "error")}


def csv_download(filename, columns, rows):
    """匯出 CSV（UTF-8 BOM，Excel 直接開啟中文不亂碼）。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows([views.csv_safe(v) for v in r] for r in rows)
    return Response("﻿" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
