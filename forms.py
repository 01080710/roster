"""表單 / JSON 輸入解析：把 request.form、request.args、JSON 轉成業務邏輯要的參數，以及表單預設值。"""
import datetime as dt


def parse_month(s):
    """'2026-10' → (2026, 10)；空值或格式錯誤 → 本月。"""
    try:
        y, m = (int(x) for x in (s or "").split("-"))
        if 1 <= m <= 12 and 1900 <= y <= 9999:
            return y, m
    except ValueError:
        pass
    return dt.date.today().year, dt.date.today().month


def parse_date(s):
    return dt.date.fromisoformat(s) if s else None


def default_form():
    return {"start_date": dt.date.today().isoformat(), "end_date": "", "skip_non_working": True}


def default_leave_form():
    return {"shift_code": "", "start_date": dt.date.today().isoformat(), "end_date": "", "reason": ""}


def parse_leave_form(f):
    return {
        "shift_code": f.get("shift_code"),
        "start_date": f.get("start_date"),
        "end_date": f.get("end_date"),
        "reason": (f.get("reason") or "").strip() or None,
    }


def parse_submit_form(f):
    """把 HTML 表單轉成 dict（保留原字串，供重新填回表單）。"""
    return {
        "employee_id": f.get("employee_id"),
        "shift_code": f.get("shift_code"),
        "start_date": f.get("start_date"),
        "end_date": f.get("end_date"),
        "leave_approval_status": f.get("leave_approval_status") or None,
        "remarks": (f.get("remarks") or "").strip() or None,
        "skip_non_working": "skip_non_working" in f,
        "edit_key": f.get("edit_key") or None,
    }


def parse_view_filter(args):
    return {"emp": args.get("view_emp") or "", "date_from": args.get("view_from") or None,
            "date_to": args.get("view_to") or None}


def parse_api_payload(b):
    """把 JSON 請求轉成 submit_range 的參數。缺欄位丟 KeyError，日期格式錯丟 ValueError。"""
    if b.get("is_ot"):
        raise ValueError("加班請改用 POST /api/overtime，不會覆蓋當天的班")
    start = parse_date(b.get("start_date"))
    return {
        "employee_id": b["employee_id"],
        "shift_code": b["shift_code"],
        "start_date": start,
        "end_date": parse_date(b.get("end_date")) or start,
        "leave_approval_status": b.get("leave_approval_status"),
        "remarks": b.get("remarks"),
        "skip_non_working": b.get("skip_non_working", True),
    }


def default_overtime_form():
    return {"start_date": dt.date.today().isoformat(), "end_date": "", "mode": "time",
            "start_time": "", "end_time": "", "shift_code": "", "reason": ""}


def parse_overtime_form(f):
    """加班申請的表單 / JSON → create_overtime_request 的參數；方式決定用時間或加班班別。
    raw 保留原字串，供驗證失敗時填回表單。"""
    unit = f.get("mode") == "unit" if f.get("mode") else bool(f.get("shift_code"))
    start = parse_date(f.get("start_date"))
    return {
        "start_date": start,
        "end_date": parse_date(f.get("end_date")) or start,
        "shift_code": (f.get("shift_code") or None) if unit else None,
        "start_time": None if unit else (f.get("start_time") or None),
        "end_time": None if unit else (f.get("end_time") or None),
        "reason": (f.get("reason") or "").strip() or None,
        "raw": {k: f.get(k) or "" for k in ("start_date", "end_date", "start_time", "end_time", "shift_code", "reason")}
               | {"mode": "unit" if unit else "time"},
    }
