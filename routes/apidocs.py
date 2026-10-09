"""API 文件：/apidocs 顯示 Swagger UI；/apidocs/openapi.json 依目前註冊的 route 自動產生 OpenAPI 規格。

新增 route 時文件會自動出現（路徑、方法、所屬 Blueprint、@require 的權限、對應的程式位置）。
說明取自函式的 docstring：第一行是標題，其餘是說明；`---` 之後的 YAML 併入 OpenAPI 的 operation
（parameters、requestBody、responses…）。同一個函式同時處理 GET 與 POST 時，YAML 用 get: / post: 分開寫。
"""
import inspect
import json

import yaml
from flask import Blueprint, Response, abort, current_app, render_template, send_from_directory
from swagger_ui_bundle import swagger_ui_path

import config

from .common import CSRF_EXEMPT, require

bp = Blueprint("apidocs", __name__)

DOC_PERMS = ("USER_VIEW", "USER_EDIT")                   # 誰可以看 API 文件
UI_FILES = {"swagger-ui.css", "swagger-ui-bundle.js"}    # swagger-ui-bundle 套件裡實際用到的檔案
SKIP_BLUEPRINTS = {"apidocs"}
BLUEPRINT_LABELS = {"auth": "登入", "roster": "排班", "leave": "請假", "overtime": "加班", "dim": "主檔"}

INFO = """排班系統所有網址，依 Blueprint 分組：

- **API**：網址以 `/api/` 開頭，收送 JSON。錯誤一律回 `{"ok": false, "error": "原因"}`。
- **網頁**：回傳 HTML 頁面；表單送出後多半導回（302）同一頁，並在頁面上方顯示一次結果訊息。

**身分驗證**：瀏覽器已登入時會自動帶 cookie，在這裡按「Try it out」就能直接呼叫。
外部程式先 `POST /api/login` 取得 token，之後每次帶 `Authorization: Bearer <token>`。
token 有效 %d 分鐘。

**CSRF**：用 cookie 登入時，POST 要帶 `X-CSRF-Token` header 或 `csrf_token` 表單欄位（這個頁面會自動帶）；用 Bearer token 的外部程式不需要。

**注意**：「Try it out」會真的寫入資料庫（提交班表、送出申請等），請小心使用。""" % config.JWT_EXPIRE_MINUTES

COMPONENTS = {
    "securitySchemes": {
        "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        "cookieAuth": {"type": "apiKey", "in": "cookie", "name": config.JWT_COOKIE_NAME},
    },
    "schemas": {
        "Error": {"type": "object", "properties": {"ok": {"type": "boolean", "example": False},
                                                   "error": {"type": "string", "example": "請選擇假別與開始日期"}}},
    },
    "responses": {
        "BadRequest": {"description": "輸入不合法或不符合業務規則",
                       "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
    },
}
_ERROR_JSON = {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}


def _parse_doc(view):
    """docstring → (標題, 說明, YAML dict)。"""
    doc = inspect.getdoc(view) or ""
    text, _, spec = doc.partition("\n---\n")
    title, _, desc = text.partition("\n")
    return title.strip(), desc.strip(), (yaml.safe_load(spec) or {}) if spec else {}


def _operation(rule, view, method, is_api):
    title, desc, spec = _parse_doc(view)
    if method in spec and isinstance(spec[method], dict):     # get: / post: 分開寫
        spec = spec[method]
    elif any(m in spec for m in ("get", "post")):
        spec = {}
    op = dict(spec)
    perms = getattr(view, "required_perms", None)
    module = view.__module__.replace(".", "/") + ".py"
    notes = [x for x in (desc, op.pop("description", None)) if x]
    notes.append(f"**權限**：{' + '.join(f'`{p}`' for p in perms) or '登入即可'}" if perms is not None else "**權限**：不需登入")
    notes.append(f"**程式**：`{module}` 的 `{view.__name__}()`")

    op.setdefault("summary", title or view.__name__)
    op["description"] = "\n\n".join(notes)
    op["operationId"] = f"{rule.endpoint}.{method}" if len(_methods(rule)) > 1 else rule.endpoint
    group = BLUEPRINT_LABELS.get(rule.endpoint.split(".")[0], rule.endpoint.split(".")[0])
    op["tags"] = [f"{'API' if is_api else '網頁'}：{group}"]
    op["security"] = [{"cookieAuth": []}, {"bearerAuth": []}] if perms is not None else []

    # 路徑參數（<kind>、<request_id>…）自動補上
    params = list(op.get("parameters") or [])
    named = {p.get("name") for p in params}
    params += [{"name": a, "in": "path", "required": True, "schema": {"type": "string"}}
               for a in sorted(rule.arguments) if a not in named]
    if params:
        op["parameters"] = params

    responses = {str(k): v for k, v in (op.get("responses") or {}).items()}
    if not responses:
        responses = {"200": {"description": "成功"}} if is_api or method == "get" else {"302": {"description": "處理完導回頁面"}}
    if perms is not None:
        if is_api:
            responses.setdefault("401", {"description": "未登入或 token 過期 / 無效", "content": _ERROR_JSON})
        else:
            responses.setdefault("302", {"description": "未登入：導向登入頁"})
        if perms:
            responses.setdefault("403", {"description": "權限不足"})
    if method == "post" and rule.endpoint not in CSRF_EXEMPT:
        if is_api:
            responses["403"] = {"description": " / ".join(x for x in (responses.get("403", {}).get("description"),
                                                                      "用 cookie 呼叫時缺少 CSRF token") if x)}
        else:
            responses.setdefault("400", {"description": "CSRF token 不符（頁面已過期，重新整理後再送出）"})
    op["responses"] = responses
    return op


def _methods(rule):
    return sorted(m.lower() for m in rule.methods - {"HEAD", "OPTIONS"})


def build_spec(app):
    """依 app.url_map 產生 OpenAPI 3 規格；API 排在網頁前面。"""
    rules = [r for r in app.url_map.iter_rules()
             if r.endpoint != "static" and r.endpoint.split(".")[0] not in SKIP_BLUEPRINTS]
    rules.sort(key=lambda r: (not r.rule.startswith("/api/"), r.rule))
    paths, tags = {}, []
    for rule in rules:
        view = app.view_functions[rule.endpoint]
        is_api = rule.rule.startswith("/api/")
        path = rule.rule
        for a in rule.arguments:
            path = path.replace(f"<{a}>", f"{{{a}}}").replace(f"<path:{a}>", f"{{{a}}}")
        for method in _methods(rule):
            op = _operation(rule, view, method, is_api)
            paths.setdefault(path, {})[method] = op
            if op["tags"][0] not in tags:
                tags.append(op["tags"][0])
    order = list(BLUEPRINT_LABELS.values())
    tags.sort(key=lambda t: (not t.startswith("API"), order.index(t.split("：")[1]) if t.split("：")[1] in order else 99))
    return {"openapi": "3.0.3",
            "info": {"title": "Vantage Roster Situation API", "version": "1.0", "description": INFO},
            "tags": [{"name": t} for t in tags], "paths": paths, "components": COMPONENTS}


@bp.get("/apidocs")
@require(*DOC_PERMS)
def apidocs():
    return render_template("apidocs.html")


@bp.get("/apidocs/openapi.json")
@require(*DOC_PERMS)
def openapi_json():
    # 不用 jsonify：它會把 key 排序，打亂 API / 網頁的順序。default=str：YAML 會把 2026-10-30 讀成日期
    return Response(json.dumps(build_spec(current_app), ensure_ascii=False, default=str), mimetype="application/json")


@bp.get("/apidocs/ui/<filename>")
@require(*DOC_PERMS)
def swagger_ui(filename):
    """Swagger UI 的 JS / CSS 直接由 swagger-ui-bundle 套件提供（同網域，符合 CSP）。"""
    if filename not in UI_FILES:
        abort(404)
    return send_from_directory(swagger_ui_path, filename)
