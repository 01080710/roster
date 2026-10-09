"""維度表（班別 / 員工 / 假日主檔）：查看 / 新增 / 修改 / 刪除，需 USER_EDIT 才能進入。"""
import datetime as dt
from flask import Blueprint, abort, g, redirect, render_template, request, url_for
import config
from .common import audit, can, csv_download, db, log, require

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
    meta = _dim_meta(kind)
    return render_template("dim_list.html", kind=kind, meta=meta, rows=db().dim_list(kind),
                           msg=request.args.get("msg"), msg_error=request.args.get("err") == "1")


@bp.get("/dim/<kind>/export")
@require("USER_VIEW", "USER_EDIT")
def dim_export(kind):
    meta = _dim_meta(kind)
    columns = [f["name"] for f in db().dim_fields(kind)]      # 不含 password_hash
    rows = [[r[c] for c in columns] for r in db().dim_list(kind)]
    audit("匯出主檔", "export", target=meta["table"], rows=len(rows))
    return csv_download(f"{meta['table']}_{dt.date.today():%Y%m%d}.csv", columns, rows)


@bp.route("/dim/<kind>/edit", methods=["GET", "POST"])
@require("USER_VIEW", "USER_EDIT")
def dim_edit(kind):
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
            return redirect(url_for(".dim_list", kind=kind, msg=f"已{verb} {new_key}"))
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
    _dim_meta(kind)
    key = request.form.get("key")
    if kind == "employee" and key == g.user["employee_id"]:
        return redirect(url_for(".dim_list", kind=kind, msg="不能刪除自己的帳號", err="1"))
    try:
        db().dim_delete(kind, key)
        audit("刪除主檔", "dim_delete", table=config.DIM_TABLES[kind]["table"], key=key)
        return redirect(url_for(".dim_list", kind=kind, msg=f"已刪除 {key}"))
    except ValueError as e:
        log.warning("刪除主檔失敗", extra={"action": "dim_delete", "table": config.DIM_TABLES[kind]["table"],
                                          "key": key, "error": str(e)})
        return redirect(url_for(".dim_list", kind=kind, msg=f"刪除失敗：{e}", err="1"))
