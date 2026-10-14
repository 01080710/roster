"""請假 / 加班申請的流程：預覽、送出、審核、撤回 / 取消、單號。
EMP0003（Agent）的主管是 EMP0001；EMP0002 有審核權限，但不是 EMP0003 的主管。"""
import datetime as dt

import pytest

D = dt.date


# ---------------- 請假 ----------------
def test_plan_leave_skips_weekend(rdb):
    rows, days, _ = rdb.plan_leave("EMP0003", "AL_FD", D(2026, 11, 6), D(2026, 11, 9))
    assert days == 2 and [r["roster_date"] for r in rows] == ["2026-11-06", "2026-11-09"]


def test_leave_approve_then_cancel_restores_default_shift(rdb):
    rid = rdb.create_leave_request("EMP0003", "AL_FD", D(2026, 11, 10), D(2026, 11, 11), "家庭旅遊")
    assert rdb.get_leave_request(rid)["status"] == "Pending"

    with pytest.raises(ValueError):                         # 不是他的主管
        rdb.approve_leave_request(rid, "EMP0002")
    assert rdb.approve_leave_request(rid, "EMP0001") == 2
    row = rdb.get_roster("EMP0003-20261110")
    assert (row["shift_code"], row["leave_request_id"], row["leave_fraction"]) == ("AL_FD", rid, 1.0)

    with pytest.raises(ValueError, match="需由主管取消"):    # 已核准的，本人不能自己取消
        rdb.cancel_leave_request(rid, "EMP0003")
    with pytest.raises(ValueError, match="需要填寫原因"):    # 取消已核准的一定要留原因
        rdb.cancel_leave_request(rid, "EMP0001", as_approver=True, note="  ")
    assert rdb.preview_cancel_leave(rid, "EMP0001") == [         # 預覽不寫入
        {"date": "2026-11-10", "before": "AL_FD", "after": "S0716_FD"},
        {"date": "2026-11-11", "before": "AL_FD", "after": "S0716_FD"}]
    assert rdb.get_roster("EMP0003-20261110")["shift_code"] == "AL_FD"
    assert rdb.cancel_leave_request(rid, "EMP0001", as_approver=True, note="行程取消") == 2
    assert rdb.get_leave_request(rid)["status"] == "Cancelled"
    assert rdb.get_leave_request(rid)["decision_note"] == "EMP0001 取消：行程取消"
    assert rdb.get_roster("EMP0003-20261110")["shift_code"] == "S0716_FD"   # 還原為預設班別


def test_own_pending_leave_can_be_withdrawn(rdb):
    rid = rdb.create_leave_request("EMP0003", "AL_FD", D(2026, 11, 10), D(2026, 11, 10))
    rdb.cancel_leave_request(rid, "EMP0003")
    assert rdb.get_leave_request(rid)["status"] == "Cancelled"


def test_overlapping_leave_is_rejected(rdb):
    rdb.create_leave_request("EMP0003", "AL_FD", D(2026, 11, 10), D(2026, 11, 12))
    with pytest.raises(ValueError, match="重疊"):
        rdb.create_leave_request("EMP0003", "AL_FD", D(2026, 11, 12), D(2026, 11, 13))


def test_request_ids_are_sequential_per_day(rdb):
    a = rdb.create_leave_request("EMP0003", "AL_FD", D(2026, 11, 10), D(2026, 11, 10))
    b = rdb.create_leave_request("EMP0002", "AL_FD", D(2026, 11, 10), D(2026, 11, 10))
    today = dt.date.today().strftime("%Y%m%d")
    assert (a, b) == (f"LR-{today}-001", f"LR-{today}-002")


def test_request_id_collision_retries_next_number(rdb, monkeypatch):
    """模擬兩人同時送出：第一次拿到的單號已被別人用掉，應自動換下一號。"""
    taken = rdb.create_leave_request("EMP0002", "AL_FD", D(2026, 11, 10), D(2026, 11, 10))
    real = rdb._next_request_id
    calls = iter([taken])
    monkeypatch.setattr(rdb, "_next_request_id", lambda *a: next(calls, None) or real(*a))
    rid = rdb.create_leave_request("EMP0003", "AL_FD", D(2026, 11, 10), D(2026, 11, 10))
    assert rid != taken and rdb.get_leave_request(rid)["employee_id"] == "EMP0003"


# ---------------- 加班 ----------------
def test_time_overtime_counts_hours_and_avoids_work_time(rdb):
    rdb.submit_range("EMP0002", "S0918_FD", D(2026, 11, 2), D(2026, 11, 2))      # 09:00 → 18:00
    _, days, hours = rdb.plan_overtime("EMP0002", D(2026, 11, 2), D(2026, 11, 2), start_time="18:00", end_time="21:00")
    assert (hours, days) == (3, 0.375)                                           # 8 小時 = 1 天
    with pytest.raises(ValueError):
        rdb.plan_overtime("EMP0002", D(2026, 11, 2), D(2026, 11, 2), start_time="17:00", end_time="19:00")


def test_overtime_approve_then_cancel_removes_records(rdb):
    rid = rdb.create_overtime_request("EMP0003", D(2026, 11, 7), D(2026, 11, 8), shift_code="OT_FD")
    assert rdb.approve_overtime_request(rid, "EMP0001") == 2
    assert rdb.get_overtime("EMP0003-20261107")["overtime_request_id"] == rid
    with pytest.raises(ValueError, match="需要填寫原因"):
        rdb.cancel_overtime_request(rid, "EMP0001", as_approver=True)
    assert rdb.preview_cancel_overtime(rid, "EMP0001") == [
        {"date": "2026-11-07", "before": "OT_FD", "after": None}, {"date": "2026-11-08", "before": "OT_FD", "after": None}]
    assert rdb.get_overtime("EMP0003-20261107") is not None
    assert rdb.cancel_overtime_request(rid, "EMP0001", as_approver=True, note="改期") == 2
    assert rdb.get_overtime("EMP0003-20261107") is None


def test_reasons_visible_only_to_self_and_approver(rdb):
    assert rdb.can_view_reasons("EMP0003", "EMP0003")        # 本人
    assert rdb.can_view_reasons("EMP0001", "EMP0003")        # 主管
    assert not rdb.can_view_reasons("EMP0002", "EMP0003")    # 有審核權限但不是他的主管


def test_overtime_preview_matches_submit_checks(client, rdb):
    from conftest import bearer
    h = bearer(client, "EMP0003")                # Joanne 的主管是 Peter
    q = "/api/overtime/preview?mode=unit&shift_code=OT_FD&start_date=2026-11-07"
    d = client.get(q, headers=h).get_json()
    assert d["ok"] and d["dates"] == ["2026-11-07"] and d["approvers"] == ["Peter Chang"]
    # 主管沒有 OT_APPROVE：送出會被擋，預覽也要擋（確認彈窗不能按送出）
    rdb.conn.execute("UPDATE dim_employee SET permission = 'USER_VIEW' WHERE employee_id = 'EMP0001'")
    rdb.conn.commit()
    r = client.get(q, headers=h)
    assert r.status_code == 400 and "無法登入審核" in r.get_json()["error"]


def test_cancel_approved_needs_preview_permission_and_reason(client, rdb):
    from conftest import CSRF, bearer, login
    rid = rdb.create_leave_request("EMP0003", "AL_FD", D(2026, 11, 10), D(2026, 11, 10))
    rdb.approve_leave_request(rid, "EMP0001")
    url = f"/api/leave/{rid}/cancel-preview"
    assert client.get(url, headers=bearer(client, "EMP0003")).status_code == 403     # Agent 沒有 LEAVE_APPROVE
    assert client.get(url, headers=bearer(client, "EMP0002")).status_code == 400     # 不是他的主管
    d = client.get(url, headers=bearer(client, "EMP0001")).get_json()
    assert d["days"] == [{"date": "2026-11-10", "before": "AL_FD", "after": "S0716_FD"}]
    login(client, "EMP0001")
    page = client.get("/leave").get_data(as_text=True)
    assert 'id="cancel_dialog"' in page and f'data-request-id="{rid}"' in page
    client.post(f"/leave/{rid}/cancel", data={"csrf_token": CSRF, "note": ""})   # 沒填原因：不取消
    assert rdb.get_leave_request(rid)["status"] == "Approved"
    client.post(f"/leave/{rid}/cancel", data={"csrf_token": CSRF, "note": "行程取消"})
    assert rdb.get_leave_request(rid)["status"] == "Cancelled"
