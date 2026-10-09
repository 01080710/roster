"""畫面與匯出用的資料轉換：模板 filter、總覽 / 月曆 / 明細的 view model、CSV 欄位。"""
import calendar
import datetime as dt

from config import PIVOT_YEARS_AFTER, PIVOT_YEARS_BEFORE


def utc_text(iso):
    """'2026-10-08T03:12:00+00:00' → '2026-10-08 03:12:00'"""
    return iso[:19].replace("T", " ") if iso else ""


def _str_or_none(v):
    return v if isinstance(v, str) else None


def days_text(v):
    return f"{v:g}" if v else "0"


def pivot_to_view(pivot, totals, year, month=None):
    """把 RosterDB.roster_pivot 的結果轉成模板好用的 columns / rows。
    每格是 (roster_display, situation)；每列另帶上班 / 請假 / 加班天數小計。"""
    years = list(range(year - PIVOT_YEARS_BEFORE, year + PIVOT_YEARS_AFTER + 1))
    view = {"year": year, "month": month, "years": years, "columns": [], "rows": []}
    if pivot.empty:
        return view
    display, situation = pivot["roster_display"], pivot["situation"]
    for c in display.columns:
        d = dt.date.fromisoformat(c)
        view["columns"].append({"date": c, "label": d.strftime("%m-%d"), "weekday": d.strftime("%a"),
                                "weekend": d.isoweekday() >= 6})
    for key, cells in display.iterrows():
        team, office, name, employee_id = key
        t = totals.loc[key]
        view["rows"].append({
            "team": team, "office_code": office, "full_name": name, "employee_id": employee_id,
            "work": days_text(t["work_fraction"]), "leave": days_text(t["leave_fraction"]), "ot": days_text(t["ot_fraction"]),
            "ot_hours": days_text(t["ot_hours"]) if t["ot_hours"] else "",
            "cells": [(_str_or_none(v), _str_or_none(s)) for v, s in zip(cells, situation.loc[key])],
        })
    return view


def csv_safe(v):
    """避免 Excel 把使用者輸入（備註、原因）當成公式執行。"""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def pivot_export(view):
    """總覽 → CSV 欄位與資料列；待審核的請假加註（待審）。"""
    columns = ["team", "office_code", "full_name", "上班", "請假", "加班", "加班時數"] + [
        f"{c['date']} ({c['weekday']})" for c in view["columns"]]
    rows = [[r["team"], r["office_code"], r["full_name"], r["work"], r["leave"], r["ot"], r["ot_hours"]]
            + [(f"{v}（待審）" if s == "PENDING" else v) or "" for v, s in r["cells"]]
            for r in view["rows"]]
    return columns, rows


def leave_export(requests, status_labels):
    columns = ["request_id", "employee_id", "full_name", "team", "office_code", "shift_code", "roster_display",
               "start_date", "end_date", "days", "reason", "status", "approver_id", "approver_name",
               "decided_at (UTC)", "decision_note", "created_at (UTC)"]
    rows = [[q["request_id"], q["employee_id"], q["full_name"], q["team"], q["office_code"], q["shift_code"],
             q["roster_display"], q["start_date"], q["end_date"], days_text(q["days"]), q["reason"],
             status_labels.get(q["status"], q["status"]), q["approver_id"], q["approver_name"],
             utc_text(q["decided_at"]), q["decision_note"], utc_text(q["created_at"])] for q in requests]
    return columns, rows


DETAIL_LABELS = {"work": "上班", "leave": "請假", "ot": "加班"}


def detail_view(kind, rows, title, all_people):
    """逐日明細彈窗的欄位與資料（JSON）。all_people 時多一欄姓名。"""
    columns = (["姓名"] if all_people else []) + ["日期", "星期", "日別", "班別", "時間", "工時", "天數"]
    columns += {"leave": ["狀態", "申請單"], "ot": ["方式", "申請單"]}.get(kind, []) + ["備註 / 檢查"]
    out, total = [], 0
    for r in rows:
        time = (f"{r['planned_start_local'][11:]} → {r['planned_end_local'][11:]}"
                if r.get("planned_start_local") else "")
        if r.get("leave_period"):          # 非全天假：請假時段 + 剩下的上班時段
            time = f"請假 {r['leave_period']}" + (f"（上班 {time}）" if time else "")
        day_type = r["day_type"] + (f" · {r['holiday_name']}" if r.get("holiday_name") else "")
        cells = ([r["name"]] if all_people else []) + [
            r["roster_date"], r["weekday"], day_type,
            f"{r['shift_code']} · {r['roster_display'] or ''}" if r.get("shift_code") else "—",
            time, days_text(r["planned_hours"]) if r.get("planned_hours") else "",
            "0（待審，不計入）" if r["pending"] else days_text(r["days"])]
        if kind == "leave":
            cells += ["待審核" if r["pending"] else (r["leave_approval_status"] or "—"),
                      r.get("leave_request_id") or "手動輸入"]
        elif kind == "ot":
            cells += ["整天 / 半天" if r.get("shift_code") else "時間", r.get("request_id") or "舊資料"]
        cells.append("；".join(x for x in (r.get("remarks"), r.get("check_flag")) if x))
        total += 0 if r["pending"] else (r["days"] or 0)
        out.append({"cells": cells, "pending": r["pending"]})
    return {"ok": True, "title": f"{title} · {DETAIL_LABELS[kind]}明細（共 {days_text(total)} 天）",
            "columns": columns, "rows": out}


def calendar_view(year, month, days):
    """請假月曆：週一開始的格子；heat 0–4 依當天請假人數（含待審）決定顏色深淺。"""
    first = dt.date(year, month, 1)
    prev_m = (first - dt.timedelta(days=1)).replace(day=1)
    next_m = (first + dt.timedelta(days=32)).replace(day=1)
    today = dt.date.today()
    cells = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        for d in week:
            if d.month != month:
                cells.append(None)
                continue
            people = days.get(d.isoformat(), [])
            pending = sum(1 for p in people if p["pending"])
            cells.append({"day": d.day, "date": d.isoformat(), "weekday": "一二三四五六日"[d.weekday()],
                          "today": d == today, "people": people, "approved": len(people) - pending,
                          "pending": pending, "heat": min(len(people), 4)})
    return {"year": year, "month": month, "cells": cells,
            "prev": prev_m.strftime("%Y-%m"), "next": next_m.strftime("%Y-%m")}


def with_waiting_for(requests, approvers):
    """自己的申請：待審核的加上「等誰審」，讓申請人知道單子在誰手上。"""
    names = "、".join(a["full_name"] for a in approvers[:3]) + (" 等" if len(approvers) > 3 else "")
    return [dict(q, waiting_for=names if q["status"] == "Pending" else None) for q in requests]


def edit_payload(row, overrides=None):
    """把 fact_roster 的一筆資料轉成修改彈窗要填入的值；overrides 為使用者剛送出的欄位（驗證失敗時保留）。"""
    payload = {
        "edit_key": row["roster_key"],
        "employee_id": row["employee_id"],
        "full_name": row["full_name"],
        "start_date": row["roster_date"],
        "weekday": row["weekday"],
        "shift_code": row["shift_code"],
        "leave_approval_status": row["leave_approval_status"],
        "remarks": row["remarks"],
        "roster_version": row["roster_version"],
        "updatetime": utc_text(row["updated_at"]),
    }
    for k in ("shift_code", "leave_approval_status", "remarks"):
        if overrides and k in overrides:
            payload[k] = overrides[k]
    return payload


def overtime_export(requests, status_labels):
    columns = ["request_id", "employee_id", "full_name", "team", "office_code", "start_date", "end_date",
               "shift_code", "start_time", "end_time", "days", "hours", "reason", "status", "approver_id",
               "approver_name", "decided_at (UTC)", "decision_note", "created_at (UTC)"]
    rows = [[q["request_id"], q["employee_id"], q["full_name"], q["team"], q["office_code"], q["start_date"],
             q["end_date"], q["shift_code"], q["start_time"], q["end_time"], days_text(q["days"]),
             days_text(q["hours"]) if q["hours"] else "", q["reason"], status_labels.get(q["status"], q["status"]),
             q["approver_id"], q["approver_name"], utc_text(q["decided_at"]), q["decision_note"],
             utc_text(q["created_at"])] for q in requests]
    return columns, rows
