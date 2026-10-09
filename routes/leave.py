"""請假申請：LEAVE_APPLY 申請 / 撤回自己的；LEAVE_APPROVE 審核、取消已核准。"""
import datetime as dt

from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, url_for

import config
import forms
import views

from .common import audit, can, can_leave, csv_download, db, log, require

bp = Blueprint("leave", __name__)


@bp.route("/leave", methods=["GET", "POST"])
@require("USER_VIEW")
def leave():
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
            return redirect(url_for(".leave", msg=f"已送出申請單 {rid}，等待主管審核"))
        except ValueError as e:
            log.warning("請假申請被拒", extra={"action": "leave_apply", "shift_code": form["shift_code"],
                                              "error": str(e)})
            error = str(e)

    approver = can("LEAVE_APPROVE")
    cal_year, cal_month = forms.parse_month(request.args.get("cal"))
    return render_template(
        "leave.html", form=form, error=error,
        cal=views.calendar_view(cal_year, cal_month, db().leave_calendar(cal_year, cal_month)),
        msg=request.args.get("msg"), msg_error=request.args.get("err") == "1",
        leave_groups=db().leave_shift_groups(),
        mine=views.with_waiting_for(db().leave_requests(employee_id=uid), db().leave_approvers(uid))
             if can("LEAVE_APPLY") else [],
        pending=db().pending_for_approver(uid) if approver else [],
        history=db().leave_requests(approver_id=uid, statuses=["Approved", "Rejected", "Cancelled"]) if approver else [],
    )


@bp.post("/leave/<request_id>/decide")
@require("USER_VIEW", "LEAVE_APPROVE")
def leave_decide(request_id):
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
        return redirect(url_for(".leave", msg=f"{request_id}：{e}", err="1"))
    return redirect(url_for(".leave", msg=msg))


@bp.post("/leave/<request_id>/cancel")
@require("USER_VIEW")
def leave_cancel(request_id):
    if not can_leave():
        abort(403)
    try:
        n = db().cancel_leave_request(request_id, g.user["employee_id"], can("LEAVE_APPROVE"),
                                      (request.form.get("note") or "").strip())
        # 待審核的撤回與已核准的取消都走這裡；restored_days > 0 表示班表有還原
        audit("取消請假", "leave_cancel", request_id=request_id, restored_days=n)
    except ValueError as e:
        log.warning("取消請假失敗", extra={"action": "leave_cancel", "request_id": request_id, "error": str(e)})
        return redirect(url_for(".leave", msg=f"{request_id}：{e}", err="1"))
    return redirect(url_for(".leave", msg=f"已取消 {request_id}" + (f"，班表還原 {n} 天" if n else "")))


@bp.get("/api/leave/preview")
@require("LEAVE_APPLY")
def api_leave_preview():
    """請假表單即時預覽：?shift_code=AL_FD&start_date=2026-10-12&end_date=2026-10-16"""
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
    """審核紀錄：與頁面相同的範圍（自己可審的已處理申請），不限筆數。"""
    rows = db().leave_requests(approver_id=g.user["employee_id"], statuses=["Approved", "Rejected", "Cancelled"],
                               limit=-1)
    columns, data = views.leave_export(rows, config.LEAVE_REQUEST_STATUSES)
    audit("匯出審核紀錄", "export", target="leave_history", rows=len(data))
    return csv_download(f"leave_history_{dt.date.today():%Y%m%d}.csv", columns, data)
