"""排班：提交、修改、總覽、逐日明細與匯出。"""
import datetime as dt

from flask import Blueprint, abort, g, jsonify, render_template, request

import config
import forms
import views

from .common import (audit, can, check_agent_shift, check_leave_shift, check_own_employee, csv_download, db, log,
                     require, result_counts, shift_allowed)

bp = Blueprint("roster", __name__)


# def pivot_period():
#     """總覽的 ?year=&month=；month 空值或不合法 → 全年（None）。"""
#     year = request.args.get("year", type=int) or dt.date.today().year
#     month = request.args.get("month", type=int)
#     return year, month if month in range(1, 13) else None

def pivot_period():
    """總覽的 ?year=&month=；沒帶 month → 當月；month 空值或不合法 → 全年（None）。"""
    today = dt.date.today()
    year = request.args.get("year", type=int) or today.year
    if "month" not in request.args:
        return year, today.month
    month = request.args.get("month", type=int)
    return year, month if month in range(1, 13) else None

@bp.route("/", methods=["GET", "POST"])
@require("USER_VIEW")
def index():
    """排班總覽
    ---
    get:
      summary: 排班總覽頁
      description: 年度 / 月份總覽（所有人），以及自己的「查詢與修改」與加班紀錄。
      parameters:
        - {name: year, in: query, schema: {type: integer, example: 2026}, description: 總覽年份，預設今年}
        - {name: month, in: query, schema: {type: integer, minimum: 1, maximum: 12}, description: 總覽月份，空白為全年}
        - {name: view_from, in: query, schema: {type: string, format: date}, description: 「查詢與修改」日期起}
        - {name: view_to, in: query, schema: {type: string, format: date}, description: 「查詢與修改」日期迄}
        - {name: edit, in: query, schema: {type: string, example: EMP0001-20261030}, description: 載入後直接開啟這筆 roster_key 的修改彈窗（需 USER_EDIT）}
      responses:
        200: {description: 排班總覽頁（HTML）}
    post:
      summary: 提交班表 / 修改一天的班（網頁表單）
      description: |
        不帶 edit_key 為「提交班表」（需 USER_CREATE），逐日寫入日期區間；帶 edit_key 為修改彈窗（需 USER_EDIT），只改那一天。
        只能提交與修改自己的排班。結果直接顯示在同一頁，不會導回。
      requestBody:
        content:
          application/x-www-form-urlencoded:
            schema:
              type: object
              required: [employee_id, shift_code, start_date]
              properties:
                employee_id: {type: string, example: EMP0001, description: 必須是登入者本人}
                shift_code: {type: string, example: S0918_FD}
                start_date: {type: string, format: date}
                end_date: {type: string, format: date, description: 只排一天可留空}
                leave_approval_status: {type: string, enum: [Approved, Pending, Rejected], description: 班別為請假時使用}
                remarks: {type: string}
                skip_non_working: {type: string, description: 有送出這個欄位（任何值）就略過休息日與國定假日}
                edit_key: {type: string, example: EMP0001-20261030, description: 修改彈窗用的 roster_key}
      responses:
        200: {description: 排班總覽頁，含逐日提交結果或錯誤訊息}
    """
    uid = g.user["employee_id"]
    employees, shift_groups = db().form_options()
    employees = [e for e in employees if e["employee_id"] == uid]   # 本頁所有「成員」下拉只有登入者
    results, error = None, None
    edit, edit_error = None, None          # edit 有值時，頁面載入後自動開啟修改彈窗
    form = dict(forms.default_form(), employee_id=uid)
    hidden = {config.CATEGORY_LABEL["OT"]}   # 加班要到加班頁申請，提交班表的下拉不列加班班別
    if not can("LEAVE_APPROVE"):           # 請假改走申請流程，班別下拉不列請假代碼
        hidden.add(config.CATEGORY_LABEL["LEAVE"])
    shift_groups = [(label, [s for s in items if shift_allowed(g.user, s)])   # Agent 的上班班別只列預設班別
                    for label, items in shift_groups if label not in hidden]
    shift_groups = [(label, items) for label, items in shift_groups if items]

    if request.method == "POST":
        posted = forms.parse_submit_form(request.form)
        if not can("USER_EDIT" if posted["edit_key"] else "USER_CREATE"):
            abort(403)
        if not posted["edit_key"]:
            form = dict(posted, employee_id=uid)
        try:
            start = forms.parse_date(posted["start_date"])
            end = forms.parse_date(posted["end_date"]) or start
            if not (posted["employee_id"] and posted["shift_code"] and start):
                raise ValueError("請選擇員工、班別與開始日期")
            if posted["employee_id"] != uid:
                raise ValueError("只能提交與修改自己的排班")
            check_leave_shift(posted["shift_code"])
            check_agent_shift(posted["employee_id"], posted["shift_code"])
            if posted["edit_key"]:
                # 修改彈窗：只改原本那一天，員工與日期不可變
                if posted["edit_key"] != f"{posted['employee_id']}-{start.isoformat().replace('-', '')}":
                    raise ValueError("修改時不可變更員工或日期")
                end, posted["skip_non_working"] = start, False
            results = db().submit_range(posted["employee_id"], posted["shift_code"], start, end,
                                        posted["leave_approval_status"], posted["remarks"],
                                        posted["skip_non_working"], allow_update=can("USER_EDIT"))
            action = "roster_edit" if posted["edit_key"] else "roster_submit"
            counts = result_counts(results)
            if counts["error"]:             # 全有或全無：有任一天失敗就整批沒寫入
                log.warning("提交班表未寫入", extra={"action": action, "counts": counts})
                error = f"有 {counts['error']} 天無法寫入，整批都沒有寫入；請看下方原因，調整後再送出"
            else:
                audit("修改班表" if posted["edit_key"] else "提交班表", action, via="web",
                      shift_code=posted["shift_code"], start_date=start, end_date=end, counts=counts)
        except ValueError as e:
            log.warning("提交班表被拒", extra={"action": "roster_submit", "error": str(e)})
            row = db().get_roster(posted["edit_key"]) if posted["edit_key"] else None
            if row is not None:
                edit, edit_error = views.edit_payload(row, posted), str(e)
            else:
                error = str(e)
    elif request.args.get("edit") and can("USER_EDIT"):   # 也支援 /?edit=<roster_key> 直接開啟彈窗
        row = db().get_roster(request.args["edit"])
        if row is None or row["employee_id"] != uid:
            error = f"找不到 {request.args['edit']}"
        else:
            edit = views.edit_payload(row)

    view = dict(forms.parse_view_filter(request.args), emp=uid)   # 查詢也只能看自己
    recent = db().recent_roster(view["emp"], view["date_from"], view["date_to"])
    recent_ot = db().recent_overtime(uid, view["date_from"], view["date_to"])

    year, month = pivot_period()
    pivot = views.pivot_to_view(*db().roster_pivot(year, month), year, month)

    summary = result_counts(results or [])
    return render_template("roster.html", employees=employees, submit_employees=employees,
                           shift_groups=shift_groups, form=form,
                           results=results, summary=summary, error=error,
                           edit=edit, edit_error=edit_error,
                           recent=recent, recent_ot=recent_ot, view=view, pivot=pivot,
                           situation_labels=config.SITUATION_LABELS)


@bp.get("/export/roster")
@require("USER_VIEW")
def export_roster():
    """匯出排班總覽（CSV）
    依目前選的年份 / 月份匯出，欄位同畫面。
    ---
    parameters:
      - {name: year, in: query, schema: {type: integer, example: 2026}, description: 預設今年}
      - {name: month, in: query, schema: {type: integer, minimum: 1, maximum: 12}, description: 空白為全年}
    responses:
      200:
        description: CSV 檔（UTF-8 BOM），檔名如 roster_2026-10.csv
        content: {text/csv: {}}
    """
    year, month = pivot_period()
    view = views.pivot_to_view(*db().roster_pivot(year, month), year, month)
    columns, rows = views.pivot_export(view)
    audit("匯出排班總覽", "export", target="roster", year=year, month=month)
    return csv_download(f"roster_{year}{f'-{month:02d}' if month else ''}.csv", columns, rows)


@bp.get("/api/roster/detail")
@require("USER_VIEW")
def api_roster_detail():
    """總覽小計的逐日明細
    排班總覽點「上班 / 請假 / 加班」數字時呼叫。columns 是表頭，rows[].cells 與 columns 一一對應；不帶 employee_id 時多一欄姓名。
    備註可能含請假 / 加班原因：別人的備註只有能審核他的主管看得到，其他人看到的是空白（檢查提醒照常顯示）。
    ---
    parameters:
      - {name: kind, in: query, required: true, schema: {type: string, enum: [work, leave, ot]}}
      - {name: year, in: query, schema: {type: integer, example: 2026}, description: 預設今年}
      - {name: month, in: query, schema: {type: integer, minimum: 1, maximum: 12}, description: 空白為全年}
      - {name: employee_id, in: query, schema: {type: string, example: EMP0001}, description: 不帶 = 所有人}
    responses:
      200:
        description: 明細
        content:
          application/json:
            example:
              ok: true
              title: Peter Chang · 2026 年 · 請假明細（共 0.5 天）
              columns: [日期, 星期, 日別, 班別, 時間, 工時, 天數, 狀態, 申請單, 備註 / 檢查]
              rows:
                - pending: false
                  cells: ["2026-10-08", Thu, Work Day, AL_H1 · 1st 0.5 AL, "", "", "0.5", Approved, LR-20261008-002, LR-20261008-002：海外旅遊]
      400: {$ref: "#/components/responses/BadRequest"}
      404:
        description: 找不到員工
        content:
          application/json:
            example: {ok: false, error: 找不到 EMP9999}
    """
    kind = request.args.get("kind")
    if kind not in views.DETAIL_LABELS:
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
    visible = {}    # 備註可能含請假 / 加班原因（個資）：別人的只有他的主管看得到
    for r in rows:
        if r["employee_id"] not in visible:
            visible[r["employee_id"]] = db().can_view_reasons(g.user["employee_id"], r["employee_id"])
        if not visible[r["employee_id"]]:
            r["remarks"] = None
    return jsonify(views.detail_view(kind, rows, title, all_people=emp_id is None))


@bp.post("/api/roster")
@require("USER_CREATE")
def api_roster():
    """提交班表
    逐日寫入日期區間，全有或全無：任一天失敗就整批不寫入，回 400 並附上逐日結果（可先用 GET /api/roster/preview 預覽）。沒有 USER_EDIT 時只能提交自己的、不能覆蓋已有排班；請假代碼需 LEAVE_APPROVE（其他人請走請假申請）；加班請改用 POST /api/overtime。
    回傳每一天的結果：action 為 created / updated / skipped / error，row 是寫入後的 fact_roster 資料。
    ---
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [employee_id, shift_code, start_date]
            properties:
              employee_id: {type: string, example: EMP0001}
              shift_code: {type: string, example: S1501_FD}
              start_date: {type: string, format: date, example: "2026-12-01"}
              end_date: {type: string, format: date, example: "2026-12-02", description: 預設同 start_date}
              leave_approval_status: {type: string, enum: [Approved, Pending, Rejected]}
              remarks: {type: string}
              skip_non_working: {type: boolean, default: true, description: 略過休息日與國定假日}
    responses:
      200:
        description: 逐日結果
        content:
          application/json:
            example:
              ok: true
              results:
                - action: created
                  date: "2026-12-01"
                  message: ""
                  row: {roster_key: EMP0001-20261201, shift_code: S1501_FD, day_type: Work Day, planned_start_local: "2026-12-01 15:00", planned_end_local: "2026-12-02 01:00", planned_hours: 9.0, work_fraction: 1.0, "...": "..."}
      400: {$ref: "#/components/responses/BadRequest"}
    """
    try:
        p = forms.parse_api_payload(request.get_json(force=True))
        check_own_employee(p["employee_id"])
        check_leave_shift(p["shift_code"])
        check_agent_shift(p["employee_id"], p["shift_code"])
        results = db().submit_range(p["employee_id"], p["shift_code"], p["start_date"], p["end_date"],
                                    p["leave_approval_status"], p["remarks"],
                                    p["skip_non_working"], allow_update=can("USER_EDIT"))
        counts = result_counts(results)
        if counts["error"]:
            log.warning("提交班表未寫入", extra={"action": "roster_submit", "via": "api", "counts": counts})
            return jsonify({"ok": False, "error": f"有 {counts['error']} 天無法寫入，整批都沒有寫入",
                            "results": results}), 400
        audit("提交班表", "roster_submit", via="api", employee_id=p["employee_id"], shift_code=p["shift_code"],
              start_date=p["start_date"], end_date=p["end_date"], counts=counts)
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        log.warning("提交班表被拒", extra={"action": "roster_submit", "via": "api", "error": str(e)})
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "results": results})


@bp.get("/api/roster/preview")
@require("USER_CREATE")
def api_roster_preview():
    """提交班表預覽
    「提交班表」按送出時先呼叫，不會寫入資料。用和 POST /api/roster 相同的檢查，回傳逐日會發生什麼：
    action 為 created（新增）/ updated（覆蓋，before 為原本的班別）/ skipped（略過）/ error（失敗）。
    有任一天 error 時 can_write 為 false：送出會整批不寫入。
    ---
    parameters:
      - {name: employee_id, in: query, required: true, schema: {type: string, example: EMP0003}}
      - {name: shift_code, in: query, required: true, schema: {type: string, example: S0716_FD}}
      - {name: start_date, in: query, required: true, schema: {type: string, format: date, example: "2026-11-02"}}
      - {name: end_date, in: query, schema: {type: string, format: date, example: "2026-11-08"}, description: 預設同 start_date}
      - {name: leave_approval_status, in: query, schema: {type: string, enum: [Approved, Pending, Rejected]}}
      - {name: skip_non_working, in: query, schema: {type: boolean, default: true}, description: 略過休息日與國定假日}
    responses:
      200:
        description: 逐日預覽
        content:
          application/json:
            example:
              ok: true
              can_write: true
              counts: {created: 1, updated: 1, skipped: 2, error: 0}
              results:
                - {date: "2026-11-02", weekday: Mon, action: updated, before: OFF_FD, shift_code: S0716_FD, message: ""}
                - {date: "2026-11-07", weekday: Sat, action: skipped, before: null, shift_code: S0716_FD, message: "略過：Rest Day"}
      400: {$ref: "#/components/responses/BadRequest"}
    """
    try:
        a = request.args
        if not (a.get("employee_id") and a.get("shift_code") and a.get("start_date")):
            raise ValueError("請選擇員工、班別與開始日期")
        p = forms.parse_api_payload({**a, "skip_non_working": a.get("skip_non_working", "1") not in ("0", "false")})
        check_own_employee(p["employee_id"])
        check_leave_shift(p["shift_code"])
        check_agent_shift(p["employee_id"], p["shift_code"])
        results = db().submit_range(p["employee_id"], p["shift_code"], p["start_date"], p["end_date"],
                                    p["leave_approval_status"] or None, None, p["skip_non_working"],
                                    allow_update=can("USER_EDIT"), dry_run=True)
    except (KeyError, ValueError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    counts = result_counts(results)
    return jsonify({"ok": True, "can_write": not counts["error"], "counts": counts,
                    "results": [{"date": r["date"], "weekday": config.WEEKDAY[dt.date.fromisoformat(r["date"]).weekday()],
                                 "action": r["action"], "before": r.get("before"), "shift_code": p["shift_code"],
                                 "message": r["message"]} for r in results]})
