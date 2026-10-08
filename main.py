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
import datetime as dt
import functools
import getpass
import hashlib
import sys

import jwt
from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for
from jinja2 import DictLoader

import config
import htmlparsing
from crud import RosterDB, parse_permissions

app = Flask(__name__)
app.jinja_loader = DictLoader(htmlparsing.TEMPLATES)
app.jinja_env.filters["utc_text"] = htmlparsing.utc_text
app.jinja_env.filters["edit_payload"] = htmlparsing.edit_payload
app.jinja_env.globals.update(
    approval_statuses=config.APPROVAL_STATUSES,
    recent_limit=config.RECENT_ROSTER_LIMIT,
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
    return {"nav_dims": dims, "current_user": g.get("user"), "token_exp": g.get("token_exp"), "can": can}


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
    employees, shift_groups = db().form_options()
    results, error = None, None
    edit, edit_error = None, None          # edit 有值時，頁面載入後自動開啟修改彈窗
    form = htmlparsing.default_form()
    submit_employees = employees
    if self_only():                        # Agent：提交表單的員工下拉只有自己
        submit_employees = [e for e in employees if e["employee_id"] == g.user["employee_id"]]
        form["employee_id"] = g.user["employee_id"]

    if request.method == "POST":
        posted = htmlparsing.parse_submit_form(request.form)
        if not can("USER_EDIT" if posted["edit_key"] else "USER_CREATE"):
            abort(403)
        if not posted["edit_key"]:
            form = dict(posted, employee_id=g.user["employee_id"]) if self_only() else posted
        try:
            start = htmlparsing.parse_date(posted["start_date"])
            end = htmlparsing.parse_date(posted["end_date"]) or start
            if not (posted["employee_id"] and posted["shift_code"] and start):
                raise ValueError("請選擇員工、班別與開始日期")
            check_own_employee(posted["employee_id"])
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
                edit, edit_error = htmlparsing.edit_payload(row, posted), str(e)
            else:
                error = str(e)
    elif request.args.get("edit") and can("USER_EDIT"):   # 也支援 /?edit=<roster_key> 直接開啟彈窗
        row = db().get_roster(request.args["edit"])
        if row is None:
            error = f"找不到 {request.args['edit']}"
        else:
            edit = htmlparsing.edit_payload(row)

    view = htmlparsing.parse_view_filter(request.args)
    if not view["emp"] and results:
        view["emp"] = request.form.get("employee_id")
    recent = db().recent_roster(view["emp"], view["date_from"], view["date_to"])

    year = request.args.get("year", type=int) or dt.date.today().year
    pivot = htmlparsing.pivot_to_view(*db().roster_pivot(year), year)

    summary = {k: sum(1 for r in results or [] if r["action"] == k)
               for k in ("created", "updated", "skipped", "error")}
    return render_template("roster.html", employees=employees, submit_employees=submit_employees,
                           shift_groups=shift_groups, form=form,
                           results=results, summary=summary, error=error,
                           edit=edit, edit_error=edit_error,
                           recent=recent, view=view, pivot=pivot,
                           situation_labels=config.SITUATION_LABELS)


@app.post("/api/roster")
@require("USER_CREATE")
def api_roster():
    """JSON 介面（需登入：cookie 或 Authorization: Bearer <token>）。
    {"employee_id":"EMP0004","shift_code":"S0918_FD","start_date":"2026-02-16","end_date":"2026-02-20"}"""
    try:
        p = htmlparsing.parse_api_payload(request.get_json(force=True))
        check_own_employee(p["employee_id"])
        results = db().submit_range(p["employee_id"], p["shift_code"], p["start_date"], p["end_date"],
                                    p["is_ot"], p["leave_approval_status"], p["remarks"],
                                    p["skip_non_working"], allow_update=can("USER_EDIT"))
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "results": results})


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
    else:
        with RosterDB() as rdb:
            rdb.init_db()
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
