"""
排班系統：SQLite + Flask

安裝：pip install -r requirements.txt     （Windows 另需 pip install tzdata）
設定密碼：py -3.12 main.py set-password <email 或 employee_id>
執行：py -3.12 main.py                     （以 waitress 啟動，可正式使用）
開發：$env:ROSTER_DEBUG = "1"; py -3.12 main.py   （Flask 開發伺服器：改程式自動重新載入，不可對外使用）
開啟：http://127.0.0.1:5000（host / port 見 config.py）

第一次執行會自動建立 roster.db，並寫入班別、假日與員工的初始資料。
登入帳號為員工 email；尚未設定密碼的員工不能登入。

驗證採用 JWT（HS256），有效時間見 config.JWT_EXPIRE_MINUTES：
- 網頁：登入後 token 存在 HttpOnly cookie
- API：POST /api/login 取得 token，之後帶 Authorization: Bearer <token>
"""
import datetime as dt
import getpass
import os
import sys
import threading
import time

from flask import Flask

import config
import routes
import views
from db import RosterDB, backup_db
from logger import cleanup_old_logs
from routes.common import close_db, log

app = Flask(__name__)     # 頁面模板在 templates/，CSS / JS 在 static/
app.secret_key = config.JWT_SECRET_KEY    # 簽章 session cookie（一次性訊息、CSRF token）
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE=config.JWT_COOKIE_SAMESITE,
                  SESSION_COOKIE_SECURE=config.JWT_COOKIE_SECURE)
app.jinja_env.filters["utc_text"] = views.utc_text
app.jinja_env.filters["edit_payload"] = views.edit_payload
app.jinja_env.filters["days"] = views.days_text
app.jinja_env.globals.update(
    approval_statuses=config.APPROVAL_STATUSES,
    leave_status_labels=config.LEAVE_REQUEST_STATUSES,
    recent_limit=config.RECENT_ROSTER_LIMIT,
    leave_limit=config.LEAVE_REQUEST_LIMIT,
    password_min_length=config.PASSWORD_MIN_LENGTH,
    jwt_expire_minutes=config.JWT_EXPIRE_MINUTES,
    all_perms=config.PERMISSIONS,
    agent_perms=config.AGENT_PERMISSIONS,
    time_step=config.TIME_STEP_MINUTES,
    time_options=[f"{m // 60:02d}:{m % 60:02d}" for m in range(0, 1440, config.TIME_STEP_MINUTES)],
    ot_min_hours=config.OT_MIN_HOURS,
    ot_full_day_hours=config.OT_FULL_DAY_HOURS,
)
app.teardown_appcontext(close_db)
routes.register(app)     # 各業務的 API 見 routes/：auth、roster、overtime、leave、dim


@app.after_request
def set_csp(response):
    """只允許載入本站的 script / CSS：就算有內容沒跳脫好，被塞進頁面的 <script> 也不會執行。
    所以模板裡不能寫 inline <script>、<style>、onclick= 等，一律放 static/。"""
    response.headers.setdefault("Content-Security-Policy", config.CONTENT_SECURITY_POLICY)
    return response



# 每日維護：啟動時一次 + 每天 config.BACKUP_HOUR 點一次（背景執行緒）：備份資料庫、清理舊日誌
def run_backup(reason):
    try:
        path, removed = backup_db(config.DB_PATH)
        log.info(f"{reason}完成", extra={"action": "backup", "path": path, "removed": removed})
    except Exception:               # 備份失敗不能讓網站停掉
        log.exception(f"{reason}失敗", extra={"action": "backup"})


def run_log_cleanup():
    try:
        removed = cleanup_old_logs(config.LOG_DIR, config.LOG_KEEP_DAYS)
        if removed:
            log.info("清理舊日誌", extra={"action": "log_cleanup", "removed": removed})
    except Exception:
        log.exception("清理舊日誌失敗", extra={"action": "log_cleanup"})


def run_maintenance(reason):
    if config.BACKUP_ENABLED:
        run_backup(reason)
    run_log_cleanup()


def start_maintenance_scheduler():
    def loop():
        while True:
            now = dt.datetime.now()
            nxt = now.replace(hour=config.BACKUP_HOUR, minute=0, second=0, microsecond=0)
            if nxt <= now:
                nxt += dt.timedelta(days=1)
            time.sleep((nxt - now).total_seconds())
            run_maintenance("每日備份")
    threading.Thread(target=loop, name="roster-maintenance", daemon=True).start()



def init_database():
    """建立 / 升級資料表；舊班表上的加班搬到 fact_overtime 時，列出需要重新提交的日子。"""
    with RosterDB() as rdb:
        moved = rdb.init_db()
    if moved:
        # 原本的班別被加班覆蓋過、無法還原，需由本人重新提交
        log.warning("舊加班已搬到 fact_overtime，這些日子的班表已清空，請重新提交原本的班",
                    extra={"action": "overtime_migration", "days": [f"{e} {d}" for e, d in moved]})


# 指令列：py -3.12 main.py set-password <email 或 employee_id>
def cli_set_password(login):
    password = getpass.getpass(f"新密碼（至少 {config.PASSWORD_MIN_LENGTH} 個字元）：")
    if password != getpass.getpass("再輸入一次："):
        sys.exit("兩次輸入的密碼不同")
    init_database()
    with RosterDB() as rdb:
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
        # debug 模式下 Flask 會開兩個行程（監看 + 實際服務），只在實際服務的那個初始化、備份與清理
        if not config.DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            log.info("系統啟動", extra={"action": "startup", "host": config.HOST, "port": config.PORT,
                                       "debug": config.DEBUG})
            init_database()
            run_maintenance("啟動備份")
            start_maintenance_scheduler()
        if config.DEBUG:
            app.run(host=config.HOST, port=config.PORT, debug=True)
        else:
            from waitress import serve      # 正式用的 WSGI 伺服器（Flask 內建的只適合開發）
            serve(app, host=config.HOST, port=config.PORT, threads=config.THREADS)
