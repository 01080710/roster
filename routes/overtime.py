"""加班申請：OT_APPLY 申請 / 撤回自己的；OT_APPROVE 審核、取消已核准。
核准後才逐日寫入 fact_overtime（與班表分開存，不會覆蓋當天的班）。"""
import datetime as dt

from flask import Blueprint, abort, g, jsonify, render_template, request

import config
import forms
import views

from .common import audit, can, can_overtime, csv_download, db, log, redirect_msg, require

bp = Blueprint("overtime", __name__)


def _create(employee_id, p):
    """送出加班申請並寫 behavior.log；加班原因只記字數。"""
    if not p["start_date"]:
        raise ValueError("請選擇加班日期")
    rid = db().create_overtime_request(employee_id, p["start_date"], p["end_date"], p["shift_code"],
                                       p["start_time"], p["end_time"], p["reason"])
    audit("送出加班申請", "overtime_apply", request_id=rid, start_date=p["start_date"], end_date=p["end_date"],
          shift_code=p["shift_code"], start_time=p["start_time"], end_time=p["end_time"],
          reason_length=len(p["reason"] or ""))
    return rid


@bp.route("/overtime", methods=["GET", "POST"])
@require("USER_VIEW")
def overtime():
    """加班
    頁面需 OT_APPLY 或 OT_APPROVE；依權限顯示待審核、我的加班、審核紀錄。
    ---
    get:
      summary: 加班頁
      responses:
        200: {description: 加班頁（HTML）}
    post:
      summary: 送出加班申請（網頁表單）
      description: 需 OT_APPLY。只能申請自己的；mode=time 填時間（一次一天），mode=unit 選加班班別（可多天）。
      requestBody:
        content:
          application/x-www-form-urlencoded:
            schema:
              type: object
              required: [mode, start_date]
              properties:
                mode: {type: string, enum: [time, unit]}
                start_date: {type: string, format: date}
                end_date: {type: string, format: date, description: 只有 mode=unit 可多天}
                start_time: {type: string, example: "18:00", description: mode=time 必填}
                end_time: {type: string, example: "21:00", description: mode=time 必填}
                shift_code: {type: string, example: OT_FD, description: mode=unit 必填}
                reason: {type: string}
      responses:
        302: {description: 送出成功：導回加班頁並顯示申請單號}
        200: {description: 驗證失敗：重新顯示加班頁與錯誤訊息}
    """
    if not can_overtime():
        abort(403)
    uid = g.user["employee_id"]
    error, form = None, forms.default_overtime_form()
    if request.method == "POST":
        if not can("OT_APPLY"):
            abort(403)
        p = forms.parse_overtime_form(request.form)
        form = p["raw"]
        try:
            rid = _create(uid, p)
            return redirect_msg(".overtime", f"已送出加班申請 {rid}，等待主管審核")
        except ValueError as e:
            log.warning("加班申請被拒", extra={"action": "overtime_apply", "error": str(e)})
            error = str(e)

    approver = can("OT_APPROVE")
    _, shift_groups = db().form_options()
    return render_template(
        "overtime.html", form=form, error=error,
        ot_shifts=next((items for label, items in shift_groups if label == config.CATEGORY_LABEL["OT"]), []),
        mine=views.with_waiting_for(db().overtime_requests(employee_id=uid), db().overtime_approvers(uid))
             if can("OT_APPLY") else [],
        pending=db().overtime_requests(approver_id=uid, statuses=["Pending"]) if approver else [],
        history=db().overtime_requests(approver_id=uid, statuses=["Approved", "Rejected", "Cancelled"])
                if approver else [],
    )


@bp.post("/overtime/<request_id>/decide")
@require("USER_VIEW", "OT_APPROVE")
def overtime_decide(request_id):
    """審核加班（核准 / 駁回）
    只能審核主管欄位（parent_id）是自己的員工的申請。核准後逐日寫入 fact_overtime（不覆蓋班表）。
    ---
    requestBody:
      content:
        application/x-www-form-urlencoded:
          schema:
            type: object
            required: [decision]
            properties:
              decision: {type: string, enum: [approve, reject]}
              decision_note: {type: string, description: 審核意見}
    responses:
      302: {description: 導回加班頁，頁面上方顯示結果或失敗原因}
      400: {description: decision 不是 approve / reject}
    """
    decision, note = request.form.get("decision"), (request.form.get("decision_note") or "").strip()
    try:
        if decision == "approve":
            n = db().approve_overtime_request(request_id, g.user["employee_id"], note)
            msg = f"已核准 {request_id}，寫入加班 {n} 天"
            audit("核准加班", "overtime_approve", request_id=request_id, overtime_days=n)
        elif decision == "reject":
            db().reject_overtime_request(request_id, g.user["employee_id"], note)
            msg = f"已駁回 {request_id}"
            audit("駁回加班", "overtime_reject", request_id=request_id)
        else:
            abort(400)
    except ValueError as e:
        log.warning("審核加班失敗", extra={"action": f"overtime_{decision}", "request_id": request_id,
                                          "error": str(e)})
        return redirect_msg(".overtime", f"{request_id}：{e}", error=True)
    return redirect_msg(".overtime", msg)


@bp.post("/overtime/<request_id>/cancel")
@require("USER_VIEW")
def overtime_cancel(request_id):
    """撤回 / 取消加班
    需 OT_APPLY 或 OT_APPROVE。待審核的：申請人本人可撤回，審核主管也可取消。已核准的：只有審核主管能取消，並刪除這張單寫入的加班。
    ---
    requestBody:
      content:
        application/x-www-form-urlencoded:
          schema:
            type: object
            properties:
              note: {type: string, description: 取消原因}
    responses:
      302: {description: 導回加班頁，頁面上方顯示結果或失敗原因}
    """
    if not can_overtime():
        abort(403)
    try:
        n = db().cancel_overtime_request(request_id, g.user["employee_id"], can("OT_APPROVE"),
                                         (request.form.get("note") or "").strip())
        # 待審核的撤回與已核准的取消都走這裡；removed_days > 0 表示有刪除已寫入的加班
        audit("取消加班", "overtime_cancel", request_id=request_id, removed_days=n)
    except ValueError as e:
        log.warning("取消加班失敗", extra={"action": "overtime_cancel", "request_id": request_id, "error": str(e)})
        return redirect_msg(".overtime", f"{request_id}：{e}", error=True)
    return redirect_msg(".overtime", f"已取消 {request_id}" + (f"，刪除加班 {n} 天" if n else ""))


@bp.post("/overtime/record/<overtime_key>/delete")
@require("USER_VIEW", "USER_EDIT")
def overtime_record_delete(overtime_key):
    """刪除舊加班資料
    沒有申請單的舊加班資料，本人可以刪除；由申請核准的加班要取消申請單。
    ---
    responses:
      302: {description: 導回排班總覽，頁面上方顯示結果或失敗原因}
    """
    row = db().get_overtime(overtime_key)
    try:
        if row is None or row["employee_id"] != g.user["employee_id"]:
            raise ValueError(f"找不到加班 {overtime_key}")
        db().delete_overtime(overtime_key)
        audit("刪除舊加班資料", "overtime_delete", overtime_key=overtime_key, overtime_date=row["overtime_date"])
    except ValueError as e:
        log.warning("刪除加班失敗", extra={"action": "overtime_delete", "overtime_key": overtime_key, "error": str(e)})
        return redirect_msg("roster.index", str(e), error=True)
    return redirect_msg("roster.index", f"已刪除 {row['overtime_date']} 的加班")


@bp.get("/api/overtime/slots")
@require("OT_APPLY")
def api_overtime_slots():
    """可選的加班時段
    加班頁選日期後呼叫：依當天的班列出可選的開始時間，每個開始時間附上可選的結束時間與時數（避開上班時間）。
    ---
    parameters:
      - {name: date, in: query, required: true, schema: {type: string, format: date, example: "2026-10-30"}}
    responses:
      200:
        description: 可選時段；shift 為當天的班，沒有排上班時為 null
        content:
          application/json:
            example:
              ok: true
              shift: S1501_FD 15:00 → 01:00
              starts:
                - value: "01:00"
                  ends: [{value: "02:00", label: "02:00", hours: 1.0}, {value: "02:30", label: "02:30", hours: 1.5}]
      400: {$ref: "#/components/responses/BadRequest"}
    """
    try:
        day = forms.parse_date(request.args.get("date"))
        if not day:
            raise ValueError("請選擇加班日期")
        slots = db().overtime_slots(g.user["employee_id"], day)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, **slots})


@bp.get("/api/overtime/preview")
@require("OT_APPLY")
def api_overtime_preview():
    """加班天數 / 時數預覽
    加班表單變更時呼叫，不會寫入資料。參數同送出加班申請。
    ---
    parameters:
      - {name: mode, in: query, schema: {type: string, enum: [time, unit]}, description: 不帶時依有沒有 shift_code 判斷}
      - {name: start_date, in: query, required: true, schema: {type: string, format: date, example: "2026-10-30"}}
      - {name: end_date, in: query, schema: {type: string, format: date}, description: 只有 mode=unit 可多天}
      - {name: start_time, in: query, schema: {type: string, example: "02:00"}, description: mode=time 必填}
      - {name: end_time, in: query, schema: {type: string, example: "05:00"}, description: mode=time 必填}
      - {name: shift_code, in: query, schema: {type: string, example: OT_FD}, description: mode=unit 必填}
    responses:
      200:
        description: 預覽結果；hours 只有 mode=time 才有
        content:
          application/json:
            example: {ok: true, days: "0.375", hours: "3", dates: ["2026-10-30"]}
      400: {$ref: "#/components/responses/BadRequest"}
    """
    try:
        p = forms.parse_overtime_form(request.args)
        if not p["start_date"]:
            raise ValueError("請選擇加班日期")
        rows, days, hours = db().plan_overtime(g.user["employee_id"], p["start_date"], p["end_date"],
                                               p["shift_code"], p["start_time"], p["end_time"])
        hit = db().overtime_overlap(g.user["employee_id"], p["start_date"], p["end_date"])
        if hit:
            raise ValueError(f"日期與加班申請單 {hit} 重疊")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "days": views.days_text(days),
                    "hours": views.days_text(hours) if hours else None,
                    "dates": [r["overtime_date"] for r in rows]})


@bp.post("/api/overtime")
@require("OT_APPLY")
def api_overtime():
    """送出加班申請
    只能申請自己的（employee_id 可省略）。時間制（start_time + end_time，一次一天）與單位制（shift_code，可多天）擇一；送出後為待審核。
    ---
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [start_date]
            properties:
              start_date: {type: string, format: date}
              end_date: {type: string, format: date, description: 只有單位制可多天}
              start_time: {type: string, example: "18:00"}
              end_time: {type: string, example: "21:00"}
              shift_code: {type: string, example: OT_FD}
              reason: {type: string}
          examples:
            時間制:
              value: {start_date: "2026-11-02", start_time: "18:00", end_time: "21:00", reason: 月底結帳}
            單位制:
              value: {start_date: "2026-11-07", end_date: "2026-11-08", shift_code: OT_FD}
    responses:
      200:
        description: 送出成功
        content:
          application/json:
            example: {ok: true, request_id: OTR-20261009-003, status: Pending}
      400: {$ref: "#/components/responses/BadRequest"}
    """
    try:
        body = request.get_json(force=True)
        if body.get("employee_id") not in (None, "", g.user["employee_id"]):
            raise ValueError("只能申請自己的加班")
        rid = _create(g.user["employee_id"], forms.parse_overtime_form(body))
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        log.warning("加班申請被拒", extra={"action": "overtime_apply", "via": "api", "error": str(e)})
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "request_id": rid, "status": "Pending"})


@bp.get("/overtime/history/export")
@require("USER_VIEW", "OT_APPROVE")
def export_overtime_history():
    """匯出加班審核紀錄（CSV）
    與頁面相同的範圍（自己可審的已處理申請），不限筆數。
    ---
    responses:
      200:
        description: CSV 檔（UTF-8 BOM），檔名如 overtime_history_20261009.csv
        content: {text/csv: {}}
    """
    rows = db().overtime_requests(approver_id=g.user["employee_id"], statuses=["Approved", "Rejected", "Cancelled"],
                                  limit=-1)
    columns, data = views.overtime_export(rows, config.LEAVE_REQUEST_STATUSES)
    audit("匯出加班審核紀錄", "export", target="overtime_history", rows=len(data))
    return csv_download(f"overtime_history_{dt.date.today():%Y%m%d}.csv", columns, data)
