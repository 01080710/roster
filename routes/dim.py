"""維度表（班別 / 員工 / 假日主檔）：查看 / 新增 / 修改 / 刪除，需 USER_EDIT 才能進入。"""
import datetime as dt
from flask import Blueprint, abort, g, render_template, request
import config
from .common import audit, can, csv_download, db, log, redirect_msg, require

bp = Blueprint("dim", __name__)


def _dim_meta(kind):
    if kind not in config.DIM_TABLES:
        abort(404)
    return config.DIM_TABLES[kind]


def _changed_fields(before, after):
    """比對存檔前後的資料列，只回傳欄位名稱（不記值）；密碼雜湊改變時記成 password。"""
    skip = {"created_at", "updated_at", "password_hash"}
    changed = sorted(k for k in after if k not in skip and before.get(k) != after[k])
    if before.get("password_hash") != after.get("password_hash"):
        changed.append("password")
    return changed


@bp.get("/dim/<kind>")
@require("USER_VIEW", "USER_EDIT")
def dim_list(kind):
    """主檔列表頁
    ---
    parameters:
      - {name: kind, in: path, required: true, schema: {type: string, enum: [shift, employee, holiday]}, description: shift = 班別、employee = 員工、holiday = 假日}
    responses:
      200: {description: 主檔列表頁（HTML）}
      404: {description: kind 不存在}
    """
    meta = _dim_meta(kind)
    return render_template("dim_list.html", kind=kind, meta=meta, rows=db().dim_list(kind))


@bp.get("/dim/<kind>/export")
@require("USER_VIEW", "USER_EDIT")
def dim_export(kind):
    """匯出主檔（CSV）
    整張表的所有欄位，不含 password_hash。
    ---
    parameters:
      - {name: kind, in: path, required: true, schema: {type: string, enum: [shift, employee, holiday]}, description: shift = 班別、employee = 員工、holiday = 假日}
    responses:
      200:
        description: CSV 檔（UTF-8 BOM），檔名如 dim_employee_20261009.csv
        content: {text/csv: {}}
      404: {description: kind 不存在}
    """
    meta = _dim_meta(kind)
    columns = [f["name"] for f in db().dim_fields(kind)]      # 不含 password_hash
    rows = [[r[c] for c in columns] for r in db().dim_list(kind)]
    audit("匯出主檔", "export", target=meta["table"], rows=len(rows))
    return csv_download(f"{meta['table']}_{dt.date.today():%Y%m%d}.csv", columns, rows)


@bp.route("/dim/<kind>/edit", methods=["GET", "POST"])
@require("USER_VIEW", "USER_EDIT")
def dim_edit(kind):
    """主檔新增 / 編輯
    不帶 key 為新增（另需 USER_CREATE），帶 key 為編輯該筆。
    ---
    get:
      summary: 主檔編輯頁
      parameters:
        - {name: kind, in: path, required: true, schema: {type: string, enum: [shift, employee, holiday]}, description: shift = 班別、employee = 員工、holiday = 假日}
        - {name: key, in: query, schema: {type: string, example: EMP0001}, description: 主鍵；不帶為新增}
      responses:
        200: {description: 編輯頁（HTML）}
        404: {description: kind 或 key 不存在}
    post:
      summary: 儲存主檔（網頁表單）
      description: 欄位依 kind 不同，與編輯頁上的欄位相同（定義見 config.DIM_TABLES 與 db.py 的資料表）。
      parameters:
        - {name: kind, in: path, required: true, schema: {type: string, enum: [shift, employee, holiday]}, description: shift = 班別、employee = 員工、holiday = 假日}
        - {name: key, in: query, schema: {type: string}, description: 主鍵；不帶為新增}
      requestBody:
        content:
          application/x-www-form-urlencoded:
            schema:
              type: object
              additionalProperties: {type: string}
              properties:
                permission: {type: array, items: {type: string}, description: 只有 employee：勾選的權限，可重複送出多個}
                new_password: {type: string, format: password, description: 只有 employee：設定 / 重設密碼，留空不變更}
      responses:
        302: {description: 儲存成功：導回列表頁}
        200: {description: 驗證失敗：重新顯示編輯頁與錯誤訊息}
    """
    meta = _dim_meta(kind)
    key = request.args.get("key") or None
    if key is None and not can("USER_CREATE"):
        abort(403)
    error = None

    if request.method == "POST":
        try:
            before = dict(db().dim_get(kind, key) or {}) if key else {}
            new_key, action = db().dim_save(kind, request.form, key)
            verb = "更新" if action == "updated" else "新增"
            after = dict(db().dim_get(kind, new_key) or {})
            audit(f"{verb}主檔", "dim_update" if action == "updated" else "dim_create", table=meta["table"],
                  key=new_key, original_key=key if key != new_key else None, fields=_changed_fields(before, after))
            return redirect_msg(".dim_list", f"已{verb} {new_key}", kind=kind)
        except ValueError as e:
            log.warning("主檔存檔失敗", extra={"action": "dim_save", "table": meta["table"], "key": key,
                                              "error": str(e)})
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


@bp.post("/dim/<kind>/delete")
@require("USER_VIEW", "USER_EDIT", "USER_DELETE")
def dim_delete(kind):
    """刪除主檔
    不能刪除自己的帳號；仍被參照的資料（有排班、有申請單、仍是別人的主管）會刪除失敗。
    ---
    parameters:
      - {name: kind, in: path, required: true, schema: {type: string, enum: [shift, employee, holiday]}, description: shift = 班別、employee = 員工、holiday = 假日}
    requestBody:
      content:
        application/x-www-form-urlencoded:
          schema:
            type: object
            required: [key]
            properties:
              key: {type: string, description: 要刪除的主鍵}
    responses:
      302: {description: 導回列表頁，頁面上方顯示結果或失敗原因}
    """
    _dim_meta(kind)
    key = request.form.get("key")
    if kind == "employee" and key == g.user["employee_id"]:
        return redirect_msg(".dim_list", "不能刪除自己的帳號", error=True, kind=kind)
    try:
        db().dim_delete(kind, key)
        audit("刪除主檔", "dim_delete", table=config.DIM_TABLES[kind]["table"], key=key)
        return redirect_msg(".dim_list", f"已刪除 {key}", kind=kind)
    except ValueError as e:
        log.warning("刪除主檔失敗", extra={"action": "dim_delete", "table": config.DIM_TABLES[kind]["table"],
                                          "key": key, "error": str(e)})
        return redirect_msg(".dim_list", f"刪除失敗：{e}", error=True, kind=kind)
