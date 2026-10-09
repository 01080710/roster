"""請假申請：LEAVE_APPLY 申請 / 撤回自己的；LEAVE_APPROVE 審核、取消已核准。"""
import datetime as dt

from flask import Blueprint, abort, g, jsonify, render_template, request

import config
import forms
import views

from .common import audit, can, can_leave, csv_download, db, log, redirect_msg, require

bp = Blueprint("leave", __name__)


@bp.route("/leave", methods=["GET", "POST"])
@require("USER_VIEW")
def leave():
    """請假
    頁面需 LEAVE_APPLY 或 LEAVE_APPROVE；依權限顯示待審核、月曆、我的請假、審核紀錄。
    ---
    get:
      summary: 請假頁
      parameters:
        - {name: cal, in: query, schema: {type: string, example: 2026-10}, description: 月曆月份（YYYY-MM），預設本月}
      responses:
        200: {description: 請假頁（HTML）}
    post:
      summary: 送出請假申請（網頁表單）
      description: 需 LEAVE_APPLY。只能申請自己的；送出後為待審核，由主管（parent_id）審核。
      requestBody:
        content:
          application/x-www-form-urlencoded:
            schema:
              type: object
              required: [shift_code, start_date]
              properties:
                shift_code: {type: string, example: AL_FD, description: 假別（請假類班別）}
                start_date: {type: string, format: date}
                end_date: {type: string, format: date, description: 只請一天可留空；半天 / 部分請假只能單日}
                reason: {type: string}
      responses:
        302: {description: 送出成功：導回請假頁並顯示申請單號}
        200: {description: 驗證失敗：重新顯示請假頁與錯誤訊息}
    """
    if not can_leave():
        abort(403)
    uid = g.user["employee_id"]
    error, form = None, forms.default_leave_form()
    if request.method == "POST":
        if not can("LEAVE_APPLY"):
            abort(403)
        form = forms.parse_leave_form(request.form)
        try:
            start = forms.parse_date(form["start_date"])
            end = forms.parse_date(form["end_date"]) or start
            if not (form["shift_code"] and start):
                raise ValueError("請選擇假別與開始日期")
            rid = db().create_leave_request(uid, form["shift_code"], start, end, form["reason"])
            # 請假原因可能含病情等個資，只記字數
            audit("送出請假", "leave_apply", request_id=rid, shift_code=form["shift_code"],
                  start_date=start, end_date=end, reason_length=len(form["reason"] or ""))
            return redirect_msg(".leave", f"已送出申請單 {rid}，等待主管審核")
        except ValueError as e:
            log.warning("請假申請被拒", extra={"action": "leave_apply", "shift_code": form["shift_code"],
                                              "error": str(e)})
            error = str(e)

    approver = can("LEAVE_APPROVE")
    cal_year, cal_month = forms.parse_month(request.args.get("cal"))
    return render_template(
        "leave.html", form=form, error=error,
        cal=views.calendar_view(cal_year, cal_month, db().leave_calendar(cal_year, cal_month)),
        leave_groups=db().leave_shift_groups(),
        mine=views.with_waiting_for(db().leave_requests(employee_id=uid), db().leave_approvers(uid))
             if can("LEAVE_APPLY") else [],
        pending=db().pending_for_approver(uid) if approver else [],
        history=db().leave_requests(approver_id=uid, statuses=["Approved", "Rejected", "Cancelled"]) if approver else [],
    )


@bp.post("/leave/<request_id>/decide")
@require("USER_VIEW", "LEAVE_APPROVE")
def leave_decide(request_id):
    """審核請假（核准 / 駁回）
    只能審核主管欄位（parent_id）是自己的員工的申請。核准後逐日寫入班表。
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
      302: {description: 導回請假頁，頁面上方顯示結果或失敗原因}
      400: {description: decision 不是 approve / reject}
    """
    decision, note = request.form.get("decision"), (request.form.get("decision_note") or "").strip()
    try:
        if decision == "approve":
            n = db().approve_leave_request(request_id, g.user["employee_id"], note)
            msg = f"已核准 {request_id}，寫入班表 {n} 天"
            audit("核准請假", "leave_approve", request_id=request_id, roster_days=n)
        elif decision == "reject":
            db().reject_leave_request(request_id, g.user["employee_id"], note)
            msg = f"已駁回 {request_id}"
            audit("駁回請假", "leave_reject", request_id=request_id)
        else:
            abort(400)
    except ValueError as e:
        log.warning("審核請假失敗", extra={"action": f"leave_{decision}", "request_id": request_id,
                                          "error": str(e)})
        return redirect_msg(".leave", f"{request_id}：{e}", error=True)
    return redirect_msg(".leave", msg)


@bp.post("/leave/<request_id>/cancel")
@require("USER_VIEW")
def leave_cancel(request_id):
    """撤回 / 取消請假
    需 LEAVE_APPLY 或 LEAVE_APPROVE。待審核的：申請人本人可撤回，審核主管也可取消。已核准的：只有審核主管能取消，班表還原為原本的班（沒有記錄時用預設班別）。
    ---
    requestBody:
      content:
        application/x-www-form-urlencoded:
          schema:
            type: object
            properties:
              note: {type: string, description: 取消原因（主管取消已核准的假時填寫）}
    responses:
      302: {description: 導回請假頁，頁面上方顯示結果或失敗原因}
    """
    if not can_leave():
        abort(403)
    try:
        n = db().cancel_leave_request(request_id, g.user["employee_id"], can("LEAVE_APPROVE"),
                                      (request.form.get("note") or "").strip())
        # 待審核的撤回與已核准的取消都走這裡；restored_days > 0 表示班表有還原
        audit("取消請假", "leave_cancel", request_id=request_id, restored_days=n)
    except ValueError as e:
        log.warning("取消請假失敗", extra={"action": "leave_cancel", "request_id": request_id, "error": str(e)})
        return redirect_msg(".leave", f"{request_id}：{e}", error=True)
    return redirect_msg(".leave", f"已取消 {request_id}" + (f"，班表還原 {n} 天" if n else ""))


@bp.get("/api/leave/preview")
@require("LEAVE_APPLY")
def api_leave_preview():
    """請假天數預覽
    請假表單選假別與日期時呼叫，不會寫入資料。依行事曆略過休息日與國定假日；非全天假會在 periods 附上當天的班與請假時段。
    ---
    parameters:
      - {name: shift_code, in: query, required: true, schema: {type: string, example: AL_FD}}
      - {name: start_date, in: query, required: true, schema: {type: string, format: date, example: "2026-11-02"}}
      - {name: end_date, in: query, schema: {type: string, format: date, example: "2026-11-04"}, description: 預設同 start_date}
    responses:
      200:
        description: 預覽結果
        content:
          application/json:
            examples:
              全天假:
                value: {ok: true, days: "3", dates: ["2026-11-02", "2026-11-03", "2026-11-04"], periods: []}
              半天假:
                value: {ok: true, days: "0.5", dates: ["2026-10-30"], periods: [{date: "2026-10-30", shift: "S1501_FD 15:00 → 01:00", leave: "15:00 → 19:30"}]}
      400: {$ref: "#/components/responses/BadRequest"}
    """
    try:
        start = forms.parse_date(request.args.get("start_date"))
        end = forms.parse_date(request.args.get("end_date")) or start
        shift_code = request.args.get("shift_code")
        if not (shift_code and start):
            raise ValueError("請選擇假別與開始日期")
        rows, days, periods = db().plan_leave(g.user["employee_id"], shift_code, start, end)
        hit = db().leave_overlap(g.user["employee_id"], start, end)
        if hit:
            raise ValueError(f"日期與申請單 {hit} 重疊")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    # periods：非全天假時附上當天的班與請假時段，例如 {"shift": "S0918_FD 09:00 → 18:00", "leave": "09:00 → 13:00"}
    return jsonify({"ok": True, "days": views.days_text(days), "dates": [r["roster_date"] for r in rows],
                    "periods": [p for p in periods if p["leave"]]})


@bp.get("/leave/history/export")
@require("USER_VIEW", "LEAVE_APPROVE")
def export_leave_history():
    """匯出請假審核紀錄（CSV）
    與頁面相同的範圍（自己可審的已處理申請），不限筆數。
    ---
    responses:
      200:
        description: CSV 檔（UTF-8 BOM），檔名如 leave_history_20261009.csv
        content: {text/csv: {}}
    """
    rows = db().leave_requests(approver_id=g.user["employee_id"], statuses=["Approved", "Rejected", "Cancelled"],
                               limit=-1)
    columns, data = views.leave_export(rows, config.LEAVE_REQUEST_STATUSES)
    audit("匯出審核紀錄", "export", target="leave_history", rows=len(data))
    return csv_download(f"leave_history_{dt.date.today():%Y%m%d}.csv", columns, data)
