"""加班申請：OT_APPLY 申請 / 撤回自己的；OT_APPROVE 審核、取消已核准。
核准後才逐日寫入 fact_overtime（與班表分開存，不會覆蓋當天的班）。"""
import datetime as dt

from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, url_for

import config
import forms
import views

from .common import audit, can, can_overtime, csv_download, db, log, require

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
            return redirect(url_for(".overtime", msg=f"已送出加班申請 {rid}，等待主管審核"))
        except ValueError as e:
            log.warning("加班申請被拒", extra={"action": "overtime_apply", "error": str(e)})
            error = str(e)

    approver = can("OT_APPROVE")
    _, shift_groups = db().form_options()
    return render_template(
        "overtime.html", form=form, error=error,
        msg=request.args.get("msg"), msg_error=request.args.get("err") == "1",
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
        return redirect(url_for(".overtime", msg=f"{request_id}：{e}", err="1"))
    return redirect(url_for(".overtime", msg=msg))


@bp.post("/overtime/<request_id>/cancel")
@require("USER_VIEW")
def overtime_cancel(request_id):
    if not can_overtime():
        abort(403)
    try:
        n = db().cancel_overtime_request(request_id, g.user["employee_id"], can("OT_APPROVE"),
                                         (request.form.get("note") or "").strip())
        # 待審核的撤回與已核准的取消都走這裡；removed_days > 0 表示有刪除已寫入的加班
        audit("取消加班", "overtime_cancel", request_id=request_id, removed_days=n)
    except ValueError as e:
        log.warning("取消加班失敗", extra={"action": "overtime_cancel", "request_id": request_id, "error": str(e)})
        return redirect(url_for(".overtime", msg=f"{request_id}：{e}", err="1"))
    return redirect(url_for(".overtime", msg=f"已取消 {request_id}" + (f"，刪除加班 {n} 天" if n else "")))


@bp.post("/overtime/record/<overtime_key>/delete")
@require("USER_VIEW", "USER_EDIT")
def overtime_record_delete(overtime_key):
    """沒有申請單的舊加班資料，本人可以刪除；由申請核准的加班要取消申請單。"""
    row = db().get_overtime(overtime_key)
    try:
        if row is None or row["employee_id"] != g.user["employee_id"]:
            raise ValueError(f"找不到加班 {overtime_key}")
        db().delete_overtime(overtime_key)
        audit("刪除舊加班資料", "overtime_delete", overtime_key=overtime_key, overtime_date=row["overtime_date"])
    except ValueError as e:
        log.warning("刪除加班失敗", extra={"action": "overtime_delete", "overtime_key": overtime_key, "error": str(e)})
        return redirect(url_for("roster.index", msg=str(e), err="1"))
    return redirect(url_for("roster.index", msg=f"已刪除 {row['overtime_date']} 的加班"))


@bp.get("/api/overtime/slots")
@require("OT_APPLY")
def api_overtime_slots():
    """填時間的加班可以選的時段（依當天的班，見 RosterDB.overtime_slots）：?date=2026-11-02"""
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
    """加班表單即時預覽：?mode=time&start_date=2026-11-02&end_date=2026-11-06&start_time=18:00&end_time=21:00"""
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
    """送出加班申請（待審核），時間制與單位制擇一：
    {"start_date":"2026-11-02","end_date":"2026-11-06","start_time":"18:00","end_time":"21:00","reason":"..."}
    {"start_date":"2026-11-07","shift_code":"OT_FD"}"""
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
    """審核紀錄：與頁面相同的範圍（自己可審的已處理申請），不限筆數。"""
    rows = db().overtime_requests(approver_id=g.user["employee_id"], statuses=["Approved", "Rejected", "Cancelled"],
                                  limit=-1)
    columns, data = views.overtime_export(rows, config.LEAVE_REQUEST_STATUSES)
    audit("匯出加班審核紀錄", "export", target="overtime_history", rows=len(data))
    return csv_download(f"overtime_history_{dt.date.today():%Y%m%d}.csv", columns, data)
