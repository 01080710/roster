"""班表提交規則（RosterDB.submit_range）。日期：2026-11-02 是週一，11-07、11-08 是週末。"""
import datetime as dt

import pytest

D = dt.date


def test_submit_range_writes_work_days_and_skips_weekend(rdb):
    results = rdb.submit_range("EMP0002", "S0918_FD", D(2026, 11, 6), D(2026, 11, 9))
    assert [(r["date"], r["action"]) for r in results] == [
        ("2026-11-06", "created"), ("2026-11-07", "skipped"), ("2026-11-08", "skipped"), ("2026-11-09", "created")]
    row = rdb.get_roster("EMP0002-20261106")
    assert (row["shift_code"], row["planned_hours"], row["work_fraction"]) == ("S0918_FD", 8.0, 1.0)


def test_public_holiday_is_skipped_by_office_calendar(rdb):
    # 2026-02-17 是 MY 的農曆新年；EMP0002 在 MY 辦公室
    [r] = rdb.submit_range("EMP0002", "S0918_FD", D(2026, 2, 17), D(2026, 2, 17))
    assert r["action"] == "skipped" and "PH" in r["message"]


def test_without_user_edit_existing_day_is_not_overwritten(rdb):
    rdb.submit_range("EMP0003", "S0716_FD", D(2026, 11, 2), D(2026, 11, 2))
    [r] = rdb.submit_range("EMP0003", "S0918_FD", D(2026, 11, 2), D(2026, 11, 2), allow_update=False)
    assert r["action"] == "error" and "USER_EDIT" in r["message"]
    assert rdb.get_roster("EMP0003-20261102")["shift_code"] == "S0716_FD"


def test_short_rest_between_shifts_is_flagged(rdb):
    rdb.submit_range("EMP0002", "S1501_FD", D(2026, 11, 2), D(2026, 11, 2))     # 15:00 → 隔天 01:00
    [r] = rdb.submit_range("EMP0002", "S0716_FD", D(2026, 11, 3), D(2026, 11, 3))   # 07:00 上班，只休 6 小時
    assert r["action"] == "created" and "距前一班僅休息 6.0 小時" in r["message"]


@pytest.mark.parametrize("start, end, message", [
    (D(2026, 11, 5), D(2026, 11, 4), "結束日期不可早於開始日期"),
    (D(2026, 1, 1), D(2026, 12, 31), "一次最多提交"),
])
def test_invalid_ranges_are_rejected(rdb, start, end, message):
    with pytest.raises(ValueError, match=message):
        rdb.submit_range("EMP0002", "S0918_FD", start, end)
