"""排班：提交、修改、總覽、逐日明細與匯出。"""
import datetime as dt

from flask import Blueprint, abort, g, jsonify, render_template, request

import config
import html_template

from .common import (audit, can, check_leave_shift, check_own_employee, csv_download, db, log, require,
                     result_counts)

bp = Blueprint("roster", __name__)


def pivot_period():
    """總覽的 ?year=&month=；month 空值或不合法 → 全年（None）。"""
    year = request.args.get("year", type=int) or dt.date.today().year
    month = request.args.get("month", type=int)
    return year, month if month in range(1, 13) else None


@bp.route("/", methods=["GET", "POST"])
@require("USER_VIEW")
def index():
    uid = g.user["employee_id"]
    employees, shift_groups = db().form_options()
    employees = [e for e in employees if e["employee_id"] == uid]   # 本頁所有「成員」下拉只有登入者
    results, error = None, None
    edit, edit_error = None, None          # edit 有值時，頁面載入後自動開啟修改彈窗
    form = dict(html_template.default_form(), employee_id=uid)
    hidden = {config.CATEGORY_LABEL["OT"]}   # 加班要到加班頁申請，提交班表的下拉不列加班班別
    if not can("LEAVE_APPROVE"):           # 請假改走申請流程，班別下拉不列請假代碼
        hidden.add(config.CATEGORY_LABEL["LEAVE"])
    shift_groups = [(label, items) for label, items in shift_groups if label not in hidden]

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
                                        posted["leave_approval_status"], posted["remarks"],
                                        posted["skip_non_working"], allow_update=can("USER_EDIT"))
            action = "roster_edit" if posted["edit_key"] else "roster_submit"
            audit("修改班表" if posted["edit_key"] else "提交班表", action, via="web",
                  shift_code=posted["shift_code"], start_date=start, end_date=end, counts=result_counts(results))
        except ValueError as e:
            log.warning("提交班表被拒", extra={"action": "roster_submit", "error": str(e)})
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
    recent_ot = db().recent_overtime(uid, view["date_from"], view["date_to"])

    year, month = pivot_period()
    pivot = html_template.pivot_to_view(*db().roster_pivot(year, month), year, month)

    summary = result_counts(results or [])
    return render_template("roster.html", employees=employees, submit_employees=employees,
                           shift_groups=shift_groups, form=form,
                           results=results, summary=summary, error=error,
                           edit=edit, edit_error=edit_error,
                           recent=recent, recent_ot=recent_ot, view=view, pivot=pivot,
                           msg=request.args.get("msg"), msg_error=request.args.get("err") == "1",
                           situation_labels=config.SITUATION_LABELS)


@bp.get("/export/roster")
@require("USER_VIEW")
def export_roster():
    """排班總覽：依目前選的年份 / 月份匯出。"""
    year, month = pivot_period()
    view = html_template.pivot_to_view(*db().roster_pivot(year, month), year, month)
    columns, rows = html_template.pivot_export(view)
    audit("匯出排班總覽", "export", target="roster", year=year, month=month)
    return csv_download(f"roster_{year}{f'-{month:02d}' if month else ''}.csv", columns, rows)


@bp.get("/api/roster/detail")
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


@bp.post("/api/roster")
@require("USER_CREATE")
def api_roster():
    """JSON 介面（需登入：cookie 或 Authorization: Bearer <token>）。
    {"employee_id":"EMP0004","shift_code":"S0918_FD","start_date":"2026-02-16","end_date":"2026-02-20"}"""
    try:
        p = html_template.parse_api_payload(request.get_json(force=True))
        check_own_employee(p["employee_id"])
        check_leave_shift(p["shift_code"])
        results = db().submit_range(p["employee_id"], p["shift_code"], p["start_date"], p["end_date"],
                                    p["leave_approval_status"], p["remarks"],
                                    p["skip_non_working"], allow_update=can("USER_EDIT"))
        audit("提交班表", "roster_submit", via="api", employee_id=p["employee_id"], shift_code=p["shift_code"],
              start_date=p["start_date"], end_date=p["end_date"], counts=result_counts(results))
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        log.warning("提交班表被拒", extra={"action": "roster_submit", "via": "api", "error": str(e)})
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "results": results})
