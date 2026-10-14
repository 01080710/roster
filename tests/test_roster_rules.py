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


# ---------------- 總覽的期間（?year=&month=） ----------------
def test_overview_defaults_to_current_month_but_keeps_full_year_in_links(client):
    from conftest import login
    login(client, "EMP0001")
    today = dt.date.today()
    year = today.year
    # 沒帶 month → 當月
    page = client.get("/").get_data(as_text=True)
    assert f'data-month="{today.month}"' in page
    # 選「全年」→ 匯出連結要帶 month=（空值），不然匯出會退回當月
    page = client.get(f"/?year={year}&month=").get_data(as_text=True)
    assert 'data-month=""' in page
    assert f"/export/roster?year={year}&amp;month=" in page
    assert client.get(f"/export/roster?year={year}&month=").headers["Content-Disposition"].endswith(f'roster_{year}.csv"')
    assert client.get(f"/export/roster?year={year}").headers["Content-Disposition"].endswith(
        f'roster_{year}-{today.month:02d}.csv"')
    # 明細 API：month 空值 → 全年
    d = client.get(f"/api/roster/detail?kind=work&year={year}&month=").get_json()
    assert d["ok"]


# ---------------- 員工資料一律 join dim_employee ----------------
def test_roster_shows_current_employee_info_after_edit(rdb):
    rdb.submit_range("EMP0003", "S0716_FD", D(2026, 11, 2), D(2026, 11, 3))
    rid = rdb.create_leave_request("EMP0003", "AL_FD", D(2026, 11, 4), D(2026, 11, 4))
    rdb.approve_leave_request(rid, "EMP0001")
    rdb.conn.execute("UPDATE dim_employee SET full_name = 'Joanne New', team = 'AO_DW' WHERE employee_id = 'EMP0003'")
    rdb.conn.commit()

    row = rdb.get_roster("EMP0003-20261102")
    assert (row["full_name"], row["team"], row["office_code"]) == ("Joanne New", "AO_DW", "MY")
    assert {r["team"] for r in rdb.recent_roster("EMP0003")} == {"AO_DW"}
    pivot, _ = rdb.roster_pivot(2026, 11)
    assert [k for k in pivot.index if k[3] == "EMP0003"] == [("AO_DW", "MY", "Joanne New", "EMP0003")]
    assert [p["name"] for p in rdb.leave_calendar(2026, 11)["2026-11-04"]] == ["Joanne New"]
    # 同 team 同期請假人數依目前的 team 計算（Laura 是 AO_DW）
    rid2 = rdb.create_leave_request("EMP0002", "AL_FD", D(2026, 11, 4), D(2026, 11, 4))
    assert next(q for q in rdb.pending_for_approver("EMP0001") if q["request_id"] == rid2)["team_off"] == 1


def test_init_db_drops_copied_employee_columns(db_path, monkeypatch, tmp_path):
    import db as db_module
    from db import RosterDB
    monkeypatch.setattr(db_module, "BACKUP_DIR", str(tmp_path / "backups"))
    with RosterDB(db_path) as old:          # 模擬舊版資料庫：fact_roster 還有複製的員工欄位
        for col in RosterDB.ROSTER_EMPLOYEE_COLUMNS:
            old.conn.execute(f"ALTER TABLE fact_roster ADD COLUMN {col} TEXT")
        old.conn.commit()
    with RosterDB(db_path) as rdb:
        rdb.init_db()
        cols = {c["name"] for c in rdb.conn.execute("PRAGMA table_info(fact_roster)")}
        assert not cols & set(RosterDB.ROSTER_EMPLOYEE_COLUMNS)
        assert rdb.submit_range("EMP0002", "S0918_FD", D(2026, 11, 2), D(2026, 11, 2))[0]["action"] == "created"
    assert [p.name.startswith("before_roster_drop_employee_columns_") for p in (tmp_path / "backups").iterdir()] == [True]

