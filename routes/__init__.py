"""依業務拆分的 router（Flask Blueprint）。新增 router 時在 BLUEPRINTS 加一行。"""
from . import apidocs, auth, dim, leave, overtime, roster
from .common import check_csrf, csrf_token, init_logging

BLUEPRINTS = [auth.bp, roster.bp, overtime.bp, leave.bp, dim.bp, apidocs.bp]


def register(app):
    init_logging(app)
    app.jinja_env.globals["csrf_token"] = csrf_token  # 模板：{{ csrf_token() }}
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)
    # 所有 POST 檢查 CSRF token；要排在 auth 的 load_user 之後（擋下時顯示的頁面需要知道登入者）
    app.before_request(check_csrf)
