"""依業務拆分的 router（Flask Blueprint）。新增 router 時在 BLUEPRINTS 加一行。"""
from . import auth, dim, leave, overtime, roster
from .common import init_logging

BLUEPRINTS = [auth.bp, roster.bp, overtime.bp, leave.bp, dim.bp]


def register(app):
    init_logging(app)
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)
