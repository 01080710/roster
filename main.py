"""
排班系統：SQLite + Flask

安裝：pip install -r requirements.txt     （Windows 另需 pip install tzdata）
設定密碼：py -3.12 main.py set-password <email 或 employee_id>
執行：py -3.12 main.py
開啟：http://127.0.0.1:5000（host / port 見 config.py）

第一次執行會自動建立 roster.db，並寫入班別、假日與員工的初始資料。
登入帳號為員工 email；尚未設定密碼的員工不能登入。

驗證採用 JWT（HS256），有效時間見 config.JWT_EXPIRE_MINUTES：
- 網頁：登入後 token 存在 HttpOnly cookie
- API：POST /api/login 取得 token，之後帶 Authorization: Bearer <token>
"""
import csv
import datetime as dt
import functools
import getpass
import hashlib
import io
import os
import sys
import threading
import time

import jwt
from flask import Flask, Response, abort, g, jsonify, redirect, render_template, request, url_for
from jinja2 import DictLoader

import config
import html_template
from api import RosterDB, backup_db, parse_permissions

app = Flask(__name__)
app.jinja_loader = DictLoader(html_template.TEMPLATES)
app.jinja_env.filters["utc_text"] = html_template.utc_text
app.jinja_env.filters["edit_payload"] = html_template.edit_payload
app.jinja_env.filters["days"] = html_template.days_text
app.jinja_env.globals.update(
    approval_statuses=config.APPROVAL_STATUSES,
    leave_status_labels=config.LEAVE_REQUEST_STATUSES,
    recent_limit=config.RECENT_ROSTER_LIMIT,
    leave_limit=config.LEAVE_REQUEST_LIMIT,
    password_min_length=config.PASSWORD_MIN_LENGTH,
    jwt_expire_minutes=config.JWT_EXPIRE_MINUTES,
    all_perms=config.PERMISSIONS,
    agent_perms=config.AGENT_PERMISSIONS,
)


def db() -> RosterDB:
    if "db" not in g:
        g.db = RosterDB(app.config.get("DB_PATH", config.DB_PATH))
    return g.db


@app.teardown_appcontext
def close_db(_):
    rdb = g.pop("db", None)
    if rdb is not None:
        rdb.close()


# =====================================================================
# JWT 登入與權限
# =====================================================================
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


@app.before_request
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


@app.after_request
def clear_bad_cookie(response):
    """cookie 裡的 token 過期或無效時順便清掉。"""
    if g.get("auth_error") and request.cookies.get(config.JWT_COOKIE_NAME):
        response.delete_cookie(config.JWT_COOKIE_NAME)
    return response


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
                return redirect(url_for("login", next=request.full_path, expired=1 if expired else None))
            if not can(*perms):
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return deco


@app.context_processor
def inject_nav():
    # 班別 / 員工 / 假日主檔需要 USER_EDIT，Agent（VIEW + CREATE）看不到
    dims = [(k, m["label"]) for k, m in config.DIM_TABLES.items()] if can("USER_EDIT") else []
    pending = db().pending_leave_count(g.user["employee_id"]) if g.get("user") and can("LEAVE_APPROVE") else 0
    return {"nav_dims": dims, "current_user": g.get("user"), "token_exp": g.get("token_exp"), "can": can,
            "can_leave": g.get("user") is not None and can_leave(), "nav_pending_leave": pending}


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    notice = "登入已逾時，請重新登入" if request.args.get("expired") else None
    if request.method == "POST":
        emp = db().authenticate(request.form.get("email"), request.form.get("password"))
        if emp is None:
            error, notice = "帳號或密碼錯誤，或帳號尚未開通", None
        else:
            nxt = request.args.get("next") or ""
            resp = redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("index"))
            resp.set_cookie(config.JWT_COOKIE_NAME, issue_token(emp),
                            max_age=config.JWT_EXPIRE_MINUTES * 60, httponly=True,
                            secure=config.JWT_COOKIE_SECURE, samesite=config.JWT_COOKIE_SAMESITE)
            return resp
    return render_template("login.html", error=error, notice=notice, email=request.form.get("email", ""))


@app.post("/api/login")
def api_login():
    """{"email": "...", "password": "..."} → {"access_token": "...", "token_type": "Bearer", "expires_in": 1800}"""
    body = request.get_json(silent=True) or {}
    emp = db().authenticate(body.get("email"), body.get("password"))
    if emp is None:
        return jsonify({"ok": False, "error": "帳號或密碼錯誤，或帳號尚未開通"}), 401
    return jsonify({"ok": True, "access_token": issue_token(emp), "token_type": "Bearer",
                    "expires_in": config.JWT_EXPIRE_MINUTES * 60})


@app.post("/logout")
def logout():
    resp = redirect(url_for("login"))
    resp.delete_cookie(config.JWT_COOKIE_NAME)
    return resp


@app.errorhandler(403)
def forbidden(_):
    return render_template("forbidden.html"), 403


# =====================================================================
# 排班提交
# =====================================================================
@app.route("/", methods=["GET", "POST"])
@require("USER_VIEW")
def index():
    uid = g.user["employee_id"]
    employees, shift_groups = db().form_options()
    employees = [e for e in employees if e["employee_id"] == uid]   # 本頁所有「成員」下拉只有登入者
    results, error = None, None
    edit, edit_error = None, None          # edit 有值時，頁面載入後自動開啟修改彈窗
    form = dict(html_template.default_form(), employee_id=uid)
    if not can("LEAVE_APPROVE"):           # 請假改走申請流程，班別下拉不列請假代碼
        shift_groups = [(label, items) for label, items in shift_groups if label != config.CATEGORY_LABEL["LEAVE"]]

    if request.method == "POST":
        posted = html_template.parse_submit_form(request.form)
        if not can("USER_EDIT" if posted["edit_key"] else "USER_CREATE"):
            abort(403)
        if not posted["edit_key"]:
            form = dict(posted, employee_id=uid)
        try:
            start = html_template.parse_date(posted["start_date"])
            end = html_template.parse_date(posted["end_date"]) or start
            if not (posted["employee_id"] and posted["shift_code"] and start):
                raise ValueError("請選擇員工、班別與開始日期")
            if posted["employee_id"] != uid:
                raise ValueError("只能提交與修改自己的排班")
            check_leave_shift(posted["shift_code"])
            if posted["edit_key"]:
                # 修改彈窗：只改原本那一天，員工與日期不可變
                if posted["edit_key"] != f"{posted['employee_id']}-{start.isoformat().replace('-', '')}":
                    raise ValueError("修改時不可變更員工或日期")
                end, posted["skip_non_working"] = start, False
            results = db().submit_range(posted["employee_id"], posted["shift_code"], start, end,
                                        posted["is_ot"], posted["leave_approval_status"], posted["remarks"],
                                        posted["skip_non_working"], allow_update=can("USER_EDIT"))
        except ValueError as e:
            row = db().get_roster(posted["edit_key"]) if posted["edit_key"] else None
            if row is not None:
                edit, edit_error = html_template.edit_payload(row, posted), str(e)
            else:
                error = str(e)
    elif request.args.get("edit") and can("USER_EDIT"):   # 也支援 /?edit=<roster_key> 直接開啟彈窗
        row = db().get_roster(request.args["edit"])
        if row is None or row["employee_id"] != uid:
            error = f"找不到 {request.args['edit']}"
        else:
            edit = html_template.edit_payload(row)

    view = dict(html_template.parse_view_filter(request.args), emp=uid)   # 查詢也只能看自己
    recent = db().recent_roster(view["emp"], view["date_from"], view["date_to"])

    year, month = pivot_period()
    pivot = html_template.pivot_to_view(*db().roster_pivot(year, month), year, month)

    summary = {k: sum(1 for r in results or [] if r["action"] == k)
               for k in ("created", "updated", "skipped", "error")}
    return render_template("roster.html", employees=employees, submit_employees=employees,
                           shift_groups=shift_groups, form=form,
                           results=results, summary=summary, error=error,
                           edit=edit, edit_error=edit_error,
                           recent=recent, view=view, pivot=pivot,
                           situation_labels=config.SITUATION_LABELS)


def pivot_period():
    """總覽的 ?year=&month=；month 空值或不合法 → 全年（None）。"""
    year = request.args.get("year", type=int) or dt.date.today().year
    month = request.args.get("month", type=int)
    return year, month if month in range(1, 13) else None


# =====================================================================
# 匯出 CSV（UTF-8 BOM，Excel 直接開啟中文不亂碼）
# =====================================================================
def csv_download(filename, columns, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows([html_template.csv_safe(v) for v in r] for r in rows)
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/export/roster")
@require("USER_VIEW")
def export_roster():
    """排班總覽：依目前選的年份 / 月份匯出。"""
    year, month = pivot_period()
    view = html_template.pivot_to_view(*db().roster_pivot(year, month), year, month)
    columns, rows = html_template.pivot_export(view)
    return csv_download(f"roster_{year}{f'-{month:02d}' if month else ''}.csv", columns, rows)


@app.get("/api/roster/detail")
@require("USER_VIEW")
def api_roster_detail():
    """總覽小計的逐日明細：?kind=work|leave|ot&year=2026&month=10&employee_id=EMP0003（不帶 employee_id = 所有人）"""
    kind = request.args.get("kind")
    if kind not in html_template.DETAIL_LABELS:
        return jsonify({"ok": False, "error": "kind 必須是 work / leave / ot"}), 400
    year, month = pivot_period()
    emp_id = request.args.get("employee_id") or None
    period = f"{year} 年" + (f" {month} 月" if month else "")
    if emp_id:
        emp = db().get_employee(emp_id)
        if emp is None:
            return jsonify({"ok": False, "error": f"找不到 {emp_id}"}), 404
        title = f"{emp['full_name']} · {period}"
    else:
        title = f"所有人 · {period}"
    rows = db().roster_detail(kind, year, month, emp_id)
    return jsonify(html_template.detail_view(kind, rows, title, all_people=emp_id is None))


@app.post("/api/roster")
@require("USER_CREATE")
def api_roster():
    """JSON 介面（需登入：cookie 或 Authorization: Bearer <token>）。
    {"employee_id":"EMP0004","shift_code":"S0918_FD","start_date":"2026-02-16","end_date":"2026-02-20"}"""
    try:
        p = html_template.parse_api_payload(request.get_json(force=True))
        check_own_employee(p["employee_id"])
        check_leave_shift(p["shift_code"])
        results = db().submit_range(p["employee_id"], p["shift_code"], p["start_date"], p["end_date"],
                                    p["is_ot"], p["leave_approval_status"], p["remarks"],
                                    p["skip_non_working"], allow_update=can("USER_EDIT"))
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "results": results})


# =====================================================================
# 請假申請：LEAVE_APPLY 申請 / 撤回自己的；LEAVE_APPROVE 審核、取消已核准
# =====================================================================
@app.route("/leave", methods=["GET", "POST"])
@require("USER_VIEW")
def leave():
    if not can_leave():
        abort(403)
    uid = g.user["employee_id"]
    error, form = None, html_template.default_leave_form()
    if request.method == "POST":
        if not can("LEAVE_APPLY"):
            abort(403)
        form = html_template.parse_leave_form(request.form)
        try:
            start = html_template.parse_date(form["start_date"])
            end = html_template.parse_date(form["end_date"]) or start
            if not (form["shift_code"] and start):
                raise ValueError("請選擇假別與開始日期")
            rid = db().create_leave_request(uid, form["shift_code"], start, end, form["reason"])
            return redirect(url_for("leave", msg=f"已送出申請單 {rid}，等待主管審核"))
        except ValueError as e:
            error = str(e)

    approver = can("LEAVE_APPROVE")
    cal_year, cal_month = html_template.parse_month(request.args.get("cal"))
    return render_template(
        "leave.html", form=form, error=error,
        cal=html_template.calendar_view(cal_year, cal_month, db().leave_calendar(cal_year, cal_month)),
        msg=request.args.get("msg"), msg_error=request.args.get("err") == "1",
        leave_groups=db().leave_shift_groups(),
        mine=html_template.with_waiting_for(db().leave_requests(employee_id=uid), db().leave_approvers(uid))
             if can("LEAVE_APPLY") else [],
        pending=db().pending_for_approver(uid) if approver else [],
        history=db().leave_requests(approver_id=uid, statuses=["Approved", "Rejected", "Cancelled"]) if approver else [],
    )


@app.post("/leave/<request_id>/decide")
@require("USER_VIEW", "LEAVE_APPROVE")
def leave_decide(request_id):
    decision, note = request.form.get("decision"), (request.form.get("decision_note") or "").strip()
    try:
        if decision == "approve":
            n = db().approve_leave_request(request_id, g.user["employee_id"], note)
            msg = f"已核准 {request_id}，寫入班表 {n} 天"
        elif decision == "reject":
            db().reject_leave_request(request_id, g.user["employee_id"], note)
            msg = f"已駁回 {request_id}"
        else:
            abort(400)
    except ValueError as e:
        return redirect(url_for("leave", msg=f"{request_id}：{e}", err="1"))
    return redirect(url_for("leave", msg=msg))


@app.post("/leave/<request_id>/cancel")
@require("USER_VIEW")
def leave_cancel(request_id):
    if not can_leave():
        abort(403)
    try:
        n = db().cancel_leave_request(request_id, g.user["employee_id"], can("LEAVE_APPROVE"),
                                      (request.form.get("note") or "").strip())
    except ValueError as e:
        return redirect(url_for("leave", msg=f"{request_id}：{e}", err="1"))
    return redirect(url_for("leave", msg=f"已取消 {request_id}" + (f"，班表還原 {n} 天" if n else "")))


@app.get("/api/leave/preview")
@require("LEAVE_APPLY")
def api_leave_preview():
    """請假表單即時預覽：?shift_code=AL_FD&start_date=2026-10-12&end_date=2026-10-16"""
    try:
        start = html_template.parse_date(request.args.get("start_date"))
        end = html_template.parse_date(request.args.get("end_date")) or start
        shift_code = request.args.get("shift_code")
        if not (shift_code and start):
            raise ValueError("請選擇假別與開始日期")
        rows, days = db().plan_leave(g.user["employee_id"], shift_code, start, end)
        hit = db().leave_overlap(g.user["employee_id"], start, end)
        if hit:
            raise ValueError(f"日期與申請單 {hit} 重疊")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "days": html_template.days_text(days), "dates": [r["roster_date"] for r in rows]})


@app.get("/leave/history/export")
@require("USER_VIEW", "LEAVE_APPROVE")
def export_leave_history():
    """審核紀錄：與頁面相同的範圍（自己可審的已處理申請），不限筆數。"""
    rows = db().leave_requests(approver_id=g.user["employee_id"], statuses=["Approved", "Rejected", "Cancelled"],
                               limit=-1)
    columns, data = html_template.leave_export(rows, config.LEAVE_REQUEST_STATUSES)
    return csv_download(f"leave_history_{dt.date.today():%Y%m%d}.csv", columns, data)


# =====================================================================
# 維度表：查看 / 新增 / 修改 / 刪除（需 USER_EDIT 才能進入）
# =====================================================================
def _dim_meta(kind):
    if kind not in config.DIM_TABLES:
        abort(404)
    return config.DIM_TABLES[kind]


@app.get("/dim/<kind>")
@require("USER_VIEW", "USER_EDIT")
def dim_list(kind):
    meta = _dim_meta(kind)
    return render_template("dim_list.html", kind=kind, meta=meta, rows=db().dim_list(kind),
                           msg=request.args.get("msg"), msg_error=request.args.get("err") == "1")


@app.get("/dim/<kind>/export")
@require("USER_VIEW", "USER_EDIT")
def dim_export(kind):
    meta = _dim_meta(kind)
    columns = [f["name"] for f in db().dim_fields(kind)]      # 不含 password_hash
    rows = [[r[c] for c in columns] for r in db().dim_list(kind)]
    return csv_download(f"{meta['table']}_{dt.date.today():%Y%m%d}.csv", columns, rows)


@app.route("/dim/<kind>/edit", methods=["GET", "POST"])
@require("USER_VIEW", "USER_EDIT")
def dim_edit(kind):
    meta = _dim_meta(kind)
    key = request.args.get("key") or None
    if key is None and not can("USER_CREATE"):
        abort(403)
    error = None

    if request.method == "POST":
        try:
            new_key, action = db().dim_save(kind, request.form, key)
            verb = "更新" if action == "updated" else "新增"
            return redirect(url_for("dim_list", kind=kind, msg=f"已{verb} {new_key}"))
        except ValueError as e:
            error = str(e)
            values = request.form.to_dict()
            values["permission"] = ",".join(request.form.getlist("permission"))
            values.pop("new_password", None)
    elif key:
        row = db().dim_get(kind, key)
        if row is None:
            abort(404)
        values = dict(row)
    else:
        values = db().dim_defaults(kind)

    return render_template("dim_edit.html", kind=kind, meta=meta, key=key, error=error,
                           fields=db().dim_fields(kind), values=values)


@app.post("/dim/<kind>/delete")
@require("USER_VIEW", "USER_EDIT", "USER_DELETE")
def dim_delete(kind):
    _dim_meta(kind)
    key = request.form.get("key")
    if kind == "employee" and key == g.user["employee_id"]:
        return redirect(url_for("dim_list", kind=kind, msg="不能刪除自己的帳號", err="1"))
    try:
        db().dim_delete(kind, key)
        return redirect(url_for("dim_list", kind=kind, msg=f"已刪除 {key}"))
    except ValueError as e:
        return redirect(url_for("dim_list", kind=kind, msg=f"刪除失敗：{e}", err="1"))


# =====================================================================
# 備份：啟動時一次 + 每天 config.BACKUP_HOUR 點一次（背景執行緒）
# =====================================================================
def run_backup(reason):
    try:
        path, removed = backup_db(config.DB_PATH)
        print(f"[backup] {reason}：{path}" + (f"（清除 {len(removed)} 份舊備份）" if removed else ""))
    except Exception as e:          # 備份失敗不能讓網站停掉
        print(f"[backup] {reason}失敗：{e}", file=sys.stderr)


def start_backup_scheduler():
    def loop():
        while True:
            now = dt.datetime.now()
            nxt = now.replace(hour=config.BACKUP_HOUR, minute=0, second=0, microsecond=0)
            if nxt <= now:
                nxt += dt.timedelta(days=1)
            time.sleep((nxt - now).total_seconds())
            run_backup("每日備份")
    threading.Thread(target=loop, name="roster-backup", daemon=True).start()


# =====================================================================
# 指令列：py -3.12 main.py set-password <email 或 employee_id>
# =====================================================================
def cli_set_password(login):
    password = getpass.getpass(f"新密碼（至少 {config.PASSWORD_MIN_LENGTH} 個字元）：")
    if password != getpass.getpass("再輸入一次："):
        sys.exit("兩次輸入的密碼不同")
    with RosterDB() as rdb:
        rdb.init_db()
        try:
            emp_id = rdb.set_password(login, password)
        except ValueError as e:
            sys.exit(str(e))
        emp = rdb.get_employee(emp_id)
    print(f"已設定 {emp_id} {emp['full_name']} 的密碼，權限：{emp['permission']}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "set-password":
        cli_set_password(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "backup":           # 手動備份：py -3.12 main.py backup
        run_backup("手動備份")
    else:
        with RosterDB() as rdb:
            rdb.init_db()
        # debug 模式下 Flask 會開兩個行程（監看 + 實際服務），只在實際服務的那個備份
        if config.BACKUP_ENABLED and (not config.DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
            run_backup("啟動備份")
            start_backup_scheduler()
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
