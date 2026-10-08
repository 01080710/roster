"""
資料表定義、初始資料與 fact_roster 的讀寫（CRUD）。
"""

from zoneinfo import ZoneInfo
import pandas as pd
import datetime as dt
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from config import (
    AGENT_PERMISSIONS, AGENT_ROLE, APPROVAL_STATUSES, CATEGORY_LABEL, DAY_PORTIONS, DAY_TYPES, DB_PATH,
    DIM_TABLES, FIELD_CHOICES, MAX_RANGE_DAYS, MIN_REST_HOURS, OFFICE_TZ, OT_FULL_DAY_HOURS,
    PASSWORD_MIN_LENGTH, PERMISSIONS, RECENT_ROSTER_LIMIT, REST_PATTERN, SHIFT_TYPES, STATUS_GROUPS,
    TEAMS, WEEKDAY,
)


def default_permissions(role):
    return AGENT_PERMISSIONS if role == AGENT_ROLE else PERMISSIONS


def parse_permissions(value):
    """'USER_VIEW,USER_CREATE' 或 list → 依 PERMISSIONS 順序的 list，忽略未知值。"""
    if isinstance(value, str):
        value = value.split(",")
    given = {p.strip() for p in value or []}
    return [p for p in PERMISSIONS if p in given]


# 1. 資料表定義
def _in(values):
    """['A', 'B'] → "'A','B'"，供 CHECK (... IN (...)) 使用。"""
    return ",".join("'" + v.replace("'", "''") + "'" for v in values)


# 注意：CHECK 限制只在建立資料表時生效；修改 config 的選項後，既有 roster.db 的限制不會自動改變
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS dim_shift_code (
    shift_code            TEXT PRIMARY KEY,
    roster_display        TEXT,
    shift_name            TEXT NOT NULL,
    category              TEXT NOT NULL CHECK (category IN ({_in(CATEGORY_LABEL)})),
    status_group          TEXT NOT NULL CHECK (status_group IN ({_in(STATUS_GROUPS)})),
    shift_type            TEXT CHECK (shift_type IN ({_in(SHIFT_TYPES)})),
    start_time            TEXT,                -- 'HH:MM'，本地時間
    end_time              TEXT,
    break_minutes         INTEGER DEFAULT 0,
    day_portion           TEXT CHECK (day_portion IN ({_in(DAY_PORTIONS)})),
    work_fraction         REAL DEFAULT 0,
    leave_fraction        REAL DEFAULT 0,
    ot_fraction           REAL DEFAULT 0,
    leave_type            TEXT,
    is_paid               INTEGER DEFAULT 1,
    deducts_leave_balance INTEGER DEFAULT 0,
    is_active             INTEGER DEFAULT 1,
    sort_order            INTEGER,
    notes                 TEXT,
    created_at            TEXT,               -- 首次建立時間（UTC）
    updated_at            TEXT                -- 最後修改時間（UTC）
);

CREATE TABLE IF NOT EXISTS dim_employee (
    employee_id             TEXT PRIMARY KEY,
    full_name               TEXT NOT NULL,
    email                   TEXT UNIQUE,
    office_code             TEXT NOT NULL CHECK (office_code IN ({_in(OFFICE_TZ)})),
    calendar_code           TEXT NOT NULL,
    team                    TEXT CHECK (team IN ({_in(TEAMS)})),
    role                    TEXT,
    brand                   TEXT,
    rest_pattern_code       TEXT CHECK (rest_pattern_code IN ({_in(REST_PATTERN)})),
    default_shift_code      TEXT REFERENCES dim_shift_code(shift_code),
    contract_type           TEXT,
    contracted_weekly_hours REAL,
    hire_date               TEXT,               -- 'YYYY-MM-DD'
    termination_date        TEXT,
    manager_id              TEXT REFERENCES dim_employee(employee_id),
    notes                   TEXT,
    permission              TEXT,               -- 逗號分隔，例如 'USER_VIEW,USER_CREATE'
    password_hash           TEXT,               -- werkzeug 雜湊；NULL 表示尚未設定密碼，不能登入
    created_at              TEXT,               -- 首次建立時間（UTC）
    updated_at              TEXT                -- 最後修改時間（UTC）
);

CREATE TABLE IF NOT EXISTS dim_holiday (
    holiday_id    TEXT PRIMARY KEY,             -- {{calendar_code}}-{{YYYYMMDD}}
    calendar_code TEXT NOT NULL,
    holiday_date  TEXT NOT NULL,                -- 'YYYY-MM-DD'
    holiday_name  TEXT NOT NULL,
    holiday_group TEXT,
    is_substitute INTEGER DEFAULT 0,
    notes         TEXT,
    created_at    TEXT,                         -- 首次建立時間（UTC）
    updated_at    TEXT,                         -- 最後修改時間（UTC）
    UNIQUE (calendar_code, holiday_date)
);

CREATE TABLE IF NOT EXISTS fact_roster (
    roster_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    roster_key            TEXT NOT NULL UNIQUE, -- {{employee_id}}-{{YYYYMMDD}}
    roster_date           TEXT NOT NULL,
    employee_id           TEXT NOT NULL REFERENCES dim_employee(employee_id),
    full_name             TEXT,
    office_code           TEXT,
    team                  TEXT,
    brand                 TEXT,
    shift_code            TEXT NOT NULL REFERENCES dim_shift_code(shift_code),
    is_ot                 INTEGER DEFAULT 0,
    status_group          TEXT,
    shift_type            TEXT,
    work_fraction         REAL,
    leave_fraction        REAL,
    ot_fraction           REAL,
    planned_start_local   TEXT,
    planned_end_local     TEXT,
    planned_start_utc     TEXT,
    planned_end_utc       TEXT,
    planned_hours         REAL,
    weekday               TEXT,
    is_rest_pattern_day   INTEGER,
    is_public_holiday     INTEGER,
    holiday_name          TEXT,
    day_type              TEXT CHECK (day_type IN ({_in(DAY_TYPES)})),
    leave_approval_status TEXT CHECK (leave_approval_status IN ({_in(APPROVAL_STATUSES)})),
    roster_version        INTEGER DEFAULT 1,
    remarks               TEXT,
    check_flag            TEXT,
    created_at            TEXT,
    updated_at            TEXT
);
CREATE INDEX IF NOT EXISTS ix_roster_emp_date ON fact_roster (employee_id, roster_date);
"""


# 2. 初始資料
def _shift(code, disp, stype, start, end, brk=60, portion="FD", note=None):
    return (code, disp, f"Shift {disp}", "SHIFT", "Work", stype, start, end, brk, portion,
            1, 0, 0, None, 1, 0, note)

def _code(code, disp, name, cat, status, portion, work, leave, ot, ltype=None, paid=1, deduct=0, note=None):
    return (code, disp, name, cat, status, "N/A", None, None, 0, portion,
            work, leave, ot, ltype, paid, deduct, note)

SEED_SHIFTS = [
    _shift("S0716_FD", "07 > 16", "Morning", "07:00", "16:00"),
    _shift("S0812_PT", "08 > 12", "Morning", "08:00", "12:00", 0, "PT", "4 小時短班"),
    _shift("S0918_FD", "09 > 18", "Morning", "09:00", "18:00"),
    _shift("S1019_FD", "10 > 19", "Morning", "10:00", "19:00"),
    _shift("S1322_FD", "13 > 22", "Night", "13:00", "22:00"),
    _shift("S1423_FD", "14 > 23", "Night", "14:00", "23:00"),
    _shift("S1501_FD", "15 > 01", "Night", "15:00", "01:00"),
    _shift("S1602_FD", "16 > 02", "Night", "16:00", "02:00"),
    _shift("S2005_FD", "20 > 05", "Midnight", "20:00", "05:00"),
    _shift("S2006_FD", "20 > 06", "Midnight", "20:00", "06:00"),
    _shift("S2107_FD", "21 > 07", "Midnight", "21:00", "07:00"),
    _shift("S2207_FD", "22 > 07", "Midnight", "22:00", "07:00"),
    _shift("S2308_FD", "23 > 08", "Midnight", "23:00", "08:00"),
    _code("OT_FD", "OT", "Over Time (full day)", "OT", "Work", "FD", 0, 0, 1),
    _code("OT_H1", "1st 0.5 OT", "Over Time 1st half", "OT", "Work", "H1", 0, 0, 0.5),
    _code("OT_H2", "2nd 0.5 OT", "Over Time 2nd half", "OT", "Work", "H2", 0, 0, 0.5),
    _code("OFF_FD", "OFF", "Regular Off", "OFF", "Rest", "FD", 0, 0, 0),
    _code("OFF_H1", "1st 0.5 Off", "Off 1st half", "OFF", "Rest", "H1", 0.5, 0, 0),
    _code("OFF_H2", "2nd 0.5 Off", "Off 2nd half", "OFF", "Rest", "H2", 0.5, 0, 0),
    _code("PH_FD", "PH", "Public Holiday", "OFF", "Rest", "FD", 0, 0, 0),
]
for lt, name, paid in [("AL", "Annual Leave", 1), ("SL", "Sick Leave", 1),
                       ("UPL", "Unpaid Leave", 0), ("EL", "Emergency Leave", 1)]:
    SEED_SHIFTS += [
        _code(f"{lt}_FD", lt, name, "LEAVE", "Leave", "FD", 0, 1, 0, lt, paid, paid),
        _code(f"{lt}_H1", f"1st 0.5 {lt}", f"{name} 1st half", "LEAVE", "Leave", "H1", 0.5, 0.5, 0, lt, paid, paid),
        _code(f"{lt}_H2", f"2nd 0.5 {lt}", f"{name} 2nd half", "LEAVE", "Leave", "H2", 0.5, 0.5, 0, lt, paid, paid),
    ]
SEED_SHIFTS += [
    _code("AL_QT", "2nd 0.25 AL", "Annual Leave quarter day", "LEAVE", "Leave", "QT", 0.75, 0.25, 0, "AL", 1, 1),
    _code("NS_FD", "NS", "No Show", "LEAVE", "Leave", "FD", 0, 1, 0, "NS", 0, 0),
]
for lt, name in [("CL", "Compassionate Leave"), ("RL", "Replacement Leave"), ("HL", "Hospitalization Leave"),
                 ("ML", "Maternity Leave"), ("PL", "Paternity Leave"), ("ESL", "Examination / Study Leave")]:
    SEED_SHIFTS.append(_code(f"{lt}_FD", lt, name, "LEAVE", "Leave", "FD", 0, 1, 0, lt, 1, 1))
SEED_SHIFTS += [
    _code("HC_FD", "Health check", "Health Check (full day)", "ACTIVITY", "Duty (off-site)", "FD", 1, 0, 0),
    _code("HC_H1", "1st Health check", "Health Check 1st half", "ACTIVITY", "Duty (off-site)", "H1", 0.5, 0, 0),
    _code("HC_H2", "2nd Health check", "Health Check 2nd half", "ACTIVITY", "Duty (off-site)", "H2", 0.5, 0, 0),
    _code("TB_FD", "TB", "Team Building", "ACTIVITY", "Duty (off-site)", "FD", 1, 0, 0),
]

SEED_HOLIDAYS = [
    ("TW", "2026-01-01", "Founding Day / New Year's Day", "New Year", 0),
    ("TW", "2026-02-16", "Lunar New Year's Eve", "Lunar New Year", 0),
    ("TW", "2026-02-17", "Lunar New Year Day 1", "Lunar New Year", 0),
    ("TW", "2026-02-18", "Lunar New Year Day 2", "Lunar New Year", 0),
    ("TW", "2026-02-19", "Lunar New Year Day 3", "Lunar New Year", 0),
    ("TW", "2026-02-20", "Lunar New Year (substitute)", "Lunar New Year", 1),
    ("MY", "2026-02-17", "Chinese New Year Day 1", "Lunar New Year", 0),
    ("MY", "2026-02-18", "Chinese New Year Day 2", "Lunar New Year", 0),
    ("VN", "2026-09-01", "National Day (adjacent day)", "National Day", 0),
    ("VN", "2026-09-02", "National Day", "National Day", 0),
]

# 來自原排班表；休息模式與預設班別為示範值，請改成實際資料
SEED_EMPLOYEES = [
    ("Omar Guerraoui", "omar.guerraoui@hytechc.com", "MA", "AO", "Agent", "S1501_FD"),
    ("Cisse Papa Amadou", "cisse.papaamadou@hytechc.com", "MA", "AO", "Agent", "S2006_FD"),
    ("Rami Abderrahman", "abderahman.rami@hytechc.com", "MA", "DW", "Agent", None),
    ("Laura Lim", "laura.lim@hytechc.com", "MY", "AO_DW", "AM", "S0918_FD"),
    ("Joanne Loy", "joanne.loy@hytechc.com", "MY", "AO", "Agent", "S0716_FD"),
    ("Liyana Pertiwi", "liyana.pertiwi@hytechc.com", "MY", "AO", "Agent", "S0716_FD"),
    ("Alex Lee", "alex.lee@hytechc.com", "MY", "AO", "Agent", "S0918_FD"),
    ("Junquan Ko", "junquan.ko@hytechc.com", "MY", "AO", "Agent", "S0918_FD"),
    ("Priyatharishini Saravanan", "priya.saravanan@hytechc.com", "MY", "AO", "Agent", "S0918_FD"),
    ("Teo Sui Kee", "suikee.teo@hytechc.com", "MY", "AO", "Agent", "S0918_FD"),
    ("Rina Tan", "rina.tan@hytechc.com", "MY", "AO", "Agent", "S0918_FD"),
    ("Vicky Nak", "vicky.nak@hytechc.com", "MY", "AO", "Agent", "S2207_FD"),
    ("Aileen Chiang", "aileen.chiang@hytechc.com", "MY", "AO", "Agent", "S1322_FD"),
    ("Ummu Sarah", "ummu.sarah@hytechc.com", "MY", "AO", "Agent", "S1322_FD"),
]


# 3. 維度表欄位型別（DIM_TABLES、FIELD_CHOICES 在 config.py）
BOOL_FIELDS = {"is_paid", "deducts_leave_balance", "is_active", "is_substitute"}
DATE_FIELDS = {"hire_date", "termination_date", "holiday_date"}
TIME_FIELDS = {"start_time", "end_time"}
FK_FIELDS = {"default_shift_code", "manager_id"}
HIDDEN_FIELDS = {"password_hash"}          # 不在維度表頁面顯示；密碼另用 new_password 設定
TIMESTAMP_FIELDS = {"created_at", "updated_at"}   # 系統自動寫入，頁面唯讀


def _minutes(hhmm):
    if not hhmm:
        return None
    h, m = hhmm.split(":")[:2]
    return int(h) * 60 + int(m)


def _iso(d):
    return d.isoformat()


def _now():
    """UTC 時間戳記，例如 '2026-10-08T03:12:00+00:00'。"""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _sql_default(dflt):
    if dflt is None:
        return None
    dflt = dflt.strip("'")
    try:
        return int(dflt)
    except ValueError:
        try:
            return float(dflt)
        except ValueError:
            return dflt


# 4. RosterDB：包住一條連線，提供排班與維度表的讀寫
class RosterDB:
    """用法：
        with RosterDB() as rdb:
            rdb.init_db()
            rdb.submit_range("EMP0004", "S0918_FD", dt.date(2026, 2, 16), dt.date(2026, 2, 20))
            rdb.dim_list("employee")
    """

    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------------- 初始化 ----------------
    def init_db(self):
        conn = self.conn
        conn.executescript(SCHEMA)
        conn.executemany(
            """INSERT OR IGNORE INTO dim_shift_code
               (shift_code, roster_display, shift_name, category, status_group, shift_type, start_time, end_time,
                break_minutes, day_portion, work_fraction, leave_fraction, ot_fraction, leave_type, is_paid,
                deducts_leave_balance, notes, sort_order)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [row + (i,) for i, row in enumerate(SEED_SHIFTS, 1)],
        )
        conn.executemany(
            """INSERT OR IGNORE INTO dim_holiday
               (holiday_id, calendar_code, holiday_date, holiday_name, holiday_group, is_substitute)
               VALUES (?,?,?,?,?,?)""",
            [(f"{c}-{d.replace('-', '')}", c, d, n, grp, s) for c, d, n, grp, s in SEED_HOLIDAYS],
        )
        conn.executemany(
            """INSERT OR IGNORE INTO dim_employee
               (employee_id, full_name, email, office_code, calendar_code, team, role,
                rest_pattern_code, default_shift_code, contract_type, contracted_weekly_hours)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [(f"EMP{i:04d}", n, e, o, o, t, r, "SAT_SUN", s, "Full-time", 40)
             for i, (n, e, o, t, r, s) in enumerate(SEED_EMPLOYEES, 1)],
        )
        # 舊的 roster.db 缺欄位時補上：權限、密碼、各維度表的建立 / 更新時間
        new_cols = {
            "dim_employee": ("permission", "password_hash", "created_at", "updated_at"),
            "dim_shift_code": ("created_at", "updated_at"),
            "dim_holiday": ("created_at", "updated_at"),
        }
        now = _now()
        for table, wanted in new_cols.items():
            cols = {c["name"] for c in conn.execute(f"PRAGMA table_info({table})")}
            for col in wanted:
                if col not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            # 初始資料與既有資料沒有時間戳記：以本次初始化時間回填
            conn.execute(f"UPDATE {table} SET created_at = COALESCE(created_at, ?), "
                         f"updated_at = COALESCE(updated_at, created_at, ?) "
                         f"WHERE created_at IS NULL OR updated_at IS NULL", (now, now))
        conn.execute(
            """UPDATE dim_employee SET permission = CASE WHEN role = 'Agent' THEN ? ELSE ? END
               WHERE permission IS NULL OR permission = ''""",
            (",".join(AGENT_PERMISSIONS), ",".join(PERMISSIONS)),
        )
        conn.commit()

    # ---------------- 帳號 ----------------
    def get_employee(self, employee_id):
        return self.conn.execute("SELECT * FROM dim_employee WHERE employee_id = ?", (employee_id,)).fetchone()

    def can_login(self, emp):
        """有密碼且未離職才能登入。"""
        return bool(emp and emp["password_hash"]
                    and not (emp["termination_date"] and emp["termination_date"] < dt.date.today().isoformat()))

    def authenticate(self, email, password):
        """帳號（email）密碼正確且可登入時回傳員工資料，否則回傳 None。"""
        emp = self.conn.execute("SELECT * FROM dim_employee WHERE lower(email) = lower(?)",
                                ((email or "").strip(),)).fetchone()
        if self.can_login(emp) and check_password_hash(emp["password_hash"], password or ""):
            return emp
        return None

    def set_password(self, login, password, permissions=None):
        """依 employee_id 或 email 設定密碼；permissions 有給時一併更新權限。回傳 employee_id。"""
        if len(password or "") < PASSWORD_MIN_LENGTH:
            raise ValueError(f"密碼至少 {PASSWORD_MIN_LENGTH} 個字元")
        emp = self.conn.execute("SELECT employee_id FROM dim_employee WHERE employee_id = ? OR lower(email) = lower(?)",
                                (login, login)).fetchone()
        if emp is None:
            raise ValueError(f"找不到員工 {login}")
        self.conn.execute("UPDATE dim_employee SET password_hash = ?, updated_at = ? WHERE employee_id = ?",
                          (generate_password_hash(password), _now(), emp["employee_id"]))
        if permissions is not None:
            self.conn.execute("UPDATE dim_employee SET permission = ? WHERE employee_id = ?",
                              (",".join(parse_permissions(permissions)), emp["employee_id"]))
        self.conn.commit()
        return emp["employee_id"]

    # ---------------- 排班 ----------------
    def build_roster_row(self, employee_id, shift_code, roster_date, is_ot=False,
                         leave_approval_status=None, remarks=None):
        """讀主檔、計算衍生欄位，回傳 (row, flags)。不允許寫入時丟出 ValueError。"""
        conn = self.conn
        emp  = conn.execute("SELECT * FROM dim_employee WHERE employee_id = ?", (employee_id,)).fetchone()
        sh   = conn.execute("SELECT * FROM dim_shift_code WHERE shift_code = ?", (shift_code,)).fetchone()
        if emp is None:
            raise ValueError(f"找不到員工 {employee_id}")
        if sh is None:
            raise ValueError(f"找不到班別 {shift_code}")
        if not sh["is_active"]:
            raise ValueError(f"班別 {shift_code} 已停用")

        ds = _iso(roster_date)
        if emp["hire_date"] and ds < emp["hire_date"]:
            raise ValueError(f"到職日為 {emp['hire_date']}，不可排 {ds}")
        if emp["termination_date"] and ds > emp["termination_date"]:
            raise ValueError(f"離職日為 {emp['termination_date']}，不可排 {ds}")

        tz_name = OFFICE_TZ.get(emp["office_code"])
        if tz_name is None:
            raise ValueError(f"辦公室 {emp['office_code']} 沒有設定時區")
        tz = ZoneInfo(tz_name)

        # 班別時間
        start_m, end_m = _minutes(sh["start_time"]), _minutes(sh["end_time"])
        start_local = end_local = start_utc = end_utc = None
        planned_hours = 0.0
        if start_m is not None and end_m is not None:
            end_date = roster_date + dt.timedelta(days=1) if end_m <= start_m else roster_date
            start_dt = dt.datetime.combine(roster_date, dt.time(start_m // 60, start_m % 60), tzinfo=tz)
            end_dt = dt.datetime.combine(end_date, dt.time(end_m // 60, end_m % 60), tzinfo=tz)
            duration_h = ((end_m - start_m) % 1440 or 1440) / 60
            planned_hours = round(duration_h - (sh["break_minutes"] or 0) / 60, 2)
            start_local = start_dt.strftime("%Y-%m-%d %H:%M")
            end_local = end_dt.strftime("%Y-%m-%d %H:%M")
            start_utc = start_dt.astimezone(dt.timezone.utc).isoformat()
            end_utc = end_dt.astimezone(dt.timezone.utc).isoformat()

        # 天數；標記加班時工時達 OT_FULL_DAY_HOURS 算 1 天，未達算 0.5 天
        work_fraction = 0 if is_ot else (sh["work_fraction"] or 0)
        if is_ot:
            ot_fraction = (1 if planned_hours >= OT_FULL_DAY_HOURS else 0.5) if planned_hours > 0 else (sh["ot_fraction"] or 1)
        else:
            ot_fraction = sh["ot_fraction"] or 0

        # 休息日與假日
        wd = roster_date.isoweekday()
        is_rest_day = wd in REST_PATTERN.get(emp["rest_pattern_code"] or "", ())
        hol = conn.execute(
            "SELECT holiday_name FROM dim_holiday WHERE calendar_code = ? AND holiday_date = ?",
            (emp["calendar_code"], ds),
        ).fetchone()
        day_type = "PH" if hol else ("Rest Day" if is_rest_day else "Work Day")

        # 檢查
        status = sh["status_group"]
        flags = []
        if day_type != "Work Day" and status == "Work" and not is_ot:
            flags.append("非工作日上班但未標 OT")
        if day_type != "Work Day" and status == "Leave":
            flags.append("非工作日請假")
        if status == "Leave" and leave_approval_status != "Approved":
            flags.append("請假未核准")
        if day_type == "Work Day" and status == "Rest" and shift_code != "PH_FD":
            flags.append("工作日排休，請確認")
        if shift_code == "PH_FD" and not hol:
            flags.append(f"排 PH 但 {emp['calendar_code']} 當天不是假日")
        if not emp["rest_pattern_code"]:
            flags.append("員工未設定休息模式")
        if start_utc:
            prev = conn.execute(
                "SELECT planned_end_utc FROM fact_roster WHERE employee_id = ? AND roster_date = ?",
                (employee_id, _iso(roster_date - dt.timedelta(days=1))),
            ).fetchone()
            if prev and prev["planned_end_utc"]:
                gap = (dt.datetime.fromisoformat(start_utc) - dt.datetime.fromisoformat(prev["planned_end_utc"]))
                gap_h = round(gap.total_seconds() / 3600, 2)
                if gap_h < MIN_REST_HOURS:
                    flags.append(f"距前一班僅休息 {gap_h} 小時")

        row = {
            "roster_key": f"{employee_id}-{ds.replace('-', '')}",
            "roster_date": ds,
            "employee_id": employee_id,
            "full_name": emp["full_name"],
            "office_code": emp["office_code"],
            "team": emp["team"],
            "brand": emp["brand"],
            "shift_code": shift_code,
            "is_ot": int(bool(is_ot)),
            "status_group": status,
            "shift_type": sh["shift_type"],
            "work_fraction": work_fraction,
            "leave_fraction": sh["leave_fraction"] or 0,
            "ot_fraction": ot_fraction,
            "planned_start_local": start_local,
            "planned_end_local": end_local,
            "planned_start_utc": start_utc,
            "planned_end_utc": end_utc,
            "planned_hours": planned_hours,
            "weekday": WEEKDAY[wd - 1],
            "is_rest_pattern_day": int(is_rest_day),
            "is_public_holiday": int(bool(hol)),
            "holiday_name": hol["holiday_name"] if hol else None,
            "day_type": day_type,
            "leave_approval_status": leave_approval_status or None,
            "remarks": remarks or None,
            "check_flag": "；".join(flags) or None,
        }
        return row, flags

    def upsert_roster(self, row):
        """同人同日已存在就更新（版本 +1），否則新增。回傳 'created' 或 'updated'。"""
        now = _now()
        exists = self.conn.execute("SELECT 1 FROM fact_roster WHERE roster_key = ?",
                                   (row["roster_key"],)).fetchone()
        cols = list(row) + ["created_at", "updated_at"]
        vals = list(row.values()) + [now, now]
        updates = ", ".join(f"{c} = excluded.{c}" for c in row if c != "roster_key")
        self.conn.execute(
            f"""INSERT INTO fact_roster ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})
                ON CONFLICT (roster_key) DO UPDATE SET {updates},
                    updated_at = excluded.updated_at,
                    roster_version = fact_roster.roster_version + 1""",
            vals,
        )
        return "updated" if exists else "created"

    def submit_range(self, employee_id, shift_code, start_date, end_date, is_ot=False,
                     leave_approval_status=None, remarks=None, skip_non_working=True, allow_update=True):
        """把同一個班別套用到日期區間內的每一天，回傳每天的結果。
        allow_update=False（沒有 USER_EDIT）時，已有排班的日子不覆蓋。"""
        if end_date < start_date:
            raise ValueError("結束日期不可早於開始日期")
        days = (end_date - start_date).days + 1
        if days > MAX_RANGE_DAYS:
            raise ValueError(f"一次最多提交 {MAX_RANGE_DAYS} 天")

        results = []
        for i in range(days):
            d = start_date + dt.timedelta(days=i)
            try:
                row, flags = self.build_roster_row(employee_id, shift_code, d, is_ot,
                                                   leave_approval_status, remarks)
                if (skip_non_working and row["day_type"] != "Work Day"
                        and row["status_group"] in ("Work", "Leave") and not is_ot):
                    results.append({"date": _iso(d), "action": "skipped",
                                    "message": f"略過：{row['day_type']}", "row": row})
                    continue
                if not allow_update and self.get_roster(row["roster_key"]) is not None:
                    raise ValueError("當天已有排班，修改需要 USER_EDIT 權限")
                action = self.upsert_roster(row)
                self.conn.commit()
                results.append({"date": _iso(d), "action": action, "message": row["check_flag"] or "", "row": row})
            except ValueError as e:
                self.conn.rollback()
                results.append({"date": _iso(d), "action": "error", "message": str(e), "row": None})
        return results

    def form_options(self):
        """表單用的在職員工清單，以及依類別分組的有效班別。"""
        employees = self.conn.execute(
            """SELECT employee_id, full_name, office_code, team, default_shift_code FROM dim_employee
               WHERE termination_date IS NULL OR termination_date >= date('now')
               ORDER BY office_code, full_name"""
        ).fetchall()
        shifts = self.conn.execute(
            "SELECT * FROM dim_shift_code WHERE is_active = 1 ORDER BY sort_order"
        ).fetchall()
        groups = {}
        for s in shifts:
            groups.setdefault(s["category"], []).append(s)
        return employees, [(CATEGORY_LABEL[k], v) for k, v in groups.items()]

    def recent_roster(self, employee_id=None, date_from=None, date_to=None, limit=RECENT_ROSTER_LIMIT):
        where, args = [], []
        if employee_id:
            where.append("employee_id = ?")
            args.append(employee_id)
        if date_from:
            where.append("roster_date >= ?")
            args.append(date_from)
        if date_to:
            where.append("roster_date <= ?")
            args.append(date_to)
        sql = "SELECT * FROM fact_roster" + (" WHERE " + " AND ".join(where) if where else "")
        return self.conn.execute(sql + " ORDER BY roster_date DESC, employee_id LIMIT ?",
                                 args + [limit]).fetchall()

    def get_roster(self, roster_key):
        return self.conn.execute("SELECT * FROM fact_roster WHERE roster_key = ?", (roster_key,)).fetchone()

    def roster_pivot(self, year):
        """當年度班表樞紐：列 = (team, office_code, full_name)，欄 = roster_date，
        值 = 班別的 roster_display 與 situation（SHIFT / LEAVE / OT / OFF / ACTIVITY，標記加班一律算 OT）。
        full_name 依 employee_id 從 dim_employee 帶出。回傳 (pivot, totals)，totals 為每人上班 / 請假 / 加班天數。"""
        roster = pd.read_sql_query(
            """SELECT r.team, r.office_code, COALESCE(e.full_name, r.employee_id) AS full_name,
                      r.roster_date, r.employee_id,
                      COALESCE(s.roster_display, r.shift_code) AS roster_display,
                      CASE WHEN r.is_ot = 1 THEN 'OT' ELSE COALESCE(s.category, 'SHIFT') END AS situation,
                      r.work_fraction, r.leave_fraction, r.ot_fraction
               FROM fact_roster r
               LEFT JOIN dim_employee e ON e.employee_id = r.employee_id
               LEFT JOIN dim_shift_code s ON s.shift_code = r.shift_code
               WHERE r.roster_date BETWEEN ? AND ?
               ORDER BY r.roster_date, r.employee_id""",
            self.conn, params=(f"{year}-01-01", f"{year}-12-31"),
        )
        if roster.empty:
            return pd.DataFrame(), pd.DataFrame()
        index = ["team", "office_code", "full_name"]
        roster[["team", "office_code"]] = roster[["team", "office_code"]].fillna("—")
        pivot = roster.pivot_table(
            index=index,
            columns="roster_date",
            values=["roster_display", "situation"],
            aggfunc="last",
        )
        totals = roster.groupby(index)[["work_fraction", "leave_fraction", "ot_fraction"]].sum()
        return pivot, totals

    # ---------------- 維度表 ----------------
    @staticmethod
    def _meta(kind):
        if kind not in DIM_TABLES:
            raise ValueError(f"未知的維度表 {kind}")
        return DIM_TABLES[kind]

    def _fk_options(self, name):
        if name == "default_shift_code":
            rows = self.conn.execute(
                "SELECT shift_code, roster_display FROM dim_shift_code ORDER BY sort_order").fetchall()
            return [(r["shift_code"], f"{r['shift_code']} · {r['roster_display']}") for r in rows]
        rows = self.conn.execute("SELECT employee_id, full_name FROM dim_employee ORDER BY employee_id").fetchall()
        return [(r["employee_id"], f"{r['employee_id']} · {r['full_name']}") for r in rows]

    def dim_fields(self, kind):
        """回傳欄位清單：name、type（text/number/date/time/bool/select/perms）、options、required、pk、default、sql_type。"""
        meta = self._meta(kind)
        fields = []
        for c in self.conn.execute(f"PRAGMA table_info({meta['table']})"):
            name, sql_type = c["name"], (c["type"] or "").upper()
            if name in HIDDEN_FIELDS:
                continue
            options = None
            if name in TIMESTAMP_FIELDS:
                ftype = "readonly"
            elif name == "permission":
                ftype, options = "perms", PERMISSIONS
            elif name in BOOL_FIELDS:
                ftype = "bool"
            elif name in DATE_FIELDS:
                ftype = "date"
            elif name in TIME_FIELDS:
                ftype = "time"
            elif name in FIELD_CHOICES:
                ftype, options = "select", [(v, v) for v in FIELD_CHOICES[name]]
            elif name in FK_FIELDS:
                ftype, options = "select", self._fk_options(name)
            elif sql_type in ("INTEGER", "REAL"):
                ftype = "number"
            else:
                ftype = "text"
            fields.append({
                "name": name, "type": ftype, "options": options, "sql_type": sql_type,
                "required": bool(c["notnull"] or c["pk"]), "pk": bool(c["pk"]),
                "default": _sql_default(c["dflt_value"]),
            })
        return fields

    def dim_defaults(self, kind):
        return {f["name"]: f["default"] for f in self.dim_fields(kind)}

    def dim_list(self, kind):
        meta = self._meta(kind)
        return self.conn.execute(f"SELECT * FROM {meta['table']} ORDER BY {meta['order']}").fetchall()

    def dim_get(self, kind, key):
        meta = self._meta(kind)
        return self.conn.execute(f"SELECT * FROM {meta['table']} WHERE {meta['pk']} = ?", (key,)).fetchone()

    def _next_employee_id(self):
        nums = [int(r[0][3:]) for r in self.conn.execute(
            "SELECT employee_id FROM dim_employee WHERE employee_id LIKE 'EMP%'") if r[0][3:].isdigit()]
        return f"EMP{max(nums, default=0) + 1:04d}"

    def dim_save(self, kind, data, original_key=None):
        """新增（original_key 為 None）或更新一筆維度資料。data 可以是表單或 dict。
        員工：permission 可多選（表單 getlist 或 list / 逗號字串），全不選時依角色套用預設；
        new_password 有填才更新密碼。
        回傳 (主鍵, 'created' | 'updated')；資料有問題時丟出 ValueError。"""
        meta = self._meta(kind)
        table, pk = meta["table"], meta["pk"]
        values = {}
        for f in self.dim_fields(kind):
            raw = data.get(f["name"])
            if f["type"] == "readonly":     # created_at / updated_at 不接受表單輸入
                continue
            if f["type"] == "perms":
                raw = data.getlist(f["name"]) if hasattr(data, "getlist") else raw
                perms = parse_permissions(raw) or default_permissions((data.get("role") or "").strip())
                values[f["name"]] = ",".join(perms)
            elif f["type"] == "bool":
                values[f["name"]] = 1 if raw in (True, 1, "1", "on", "true", "True") else 0
            elif f["type"] == "number":
                if raw in (None, ""):
                    values[f["name"]] = None
                else:
                    try:
                        values[f["name"]] = int(raw) if f["sql_type"] == "INTEGER" else float(raw)
                    except (TypeError, ValueError):
                        raise ValueError(f"{f['name']} 必須是數字") from None
            else:
                values[f["name"]] = (str(raw).strip() if raw is not None else "") or None

        if meta["pk_mode"] == "derived":   # holiday_id = {calendar_code}-{YYYYMMDD}
            if values["calendar_code"] and values["holiday_date"]:
                values[pk] = f"{values['calendar_code']}-{values['holiday_date'].replace('-', '')}"
        elif original_key:
            values[pk] = original_key      # 主鍵可能被其他表參照，不允許修改
        elif meta["pk_mode"] == "auto" and not values[pk]:
            values[pk] = self._next_employee_id()
        if kind == "shift" and values.get("sort_order") is None:
            values["sort_order"] = self.conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM dim_shift_code").fetchone()[0]

        missing = [f["name"] for f in self.dim_fields(kind) if f["required"] and values.get(f["name"]) is None]
        if missing:
            raise ValueError(f"必填欄位未填：{', '.join(missing)}")
        new_password = (data.get("new_password") or "") if kind == "employee" else ""
        if new_password:
            if len(new_password) < PASSWORD_MIN_LENGTH:
                raise ValueError(f"密碼至少 {PASSWORD_MIN_LENGTH} 個字元")
            values["password_hash"] = generate_password_hash(new_password)

        # 時間戳記由系統寫入：新增時兩個都設，修改時只更新 updated_at（created_at 不動）
        values["updated_at"] = _now()
        if not original_key:
            values["created_at"] = values["updated_at"]

        try:
            if original_key:
                if self.dim_get(kind, original_key) is None:
                    raise ValueError(f"找不到 {original_key}")
                sets = ", ".join(f"{c} = ?" for c in values)
                self.conn.execute(f"UPDATE {table} SET {sets} WHERE {pk} = ?",
                                  list(values.values()) + [original_key])
                action = "updated"
            else:
                if self.dim_get(kind, values[pk]) is not None:
                    raise ValueError(f"{values[pk]} 已存在")
                self.conn.execute(
                    f"INSERT INTO {table} ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
                    list(values.values()))
                action = "created"
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            self.conn.rollback()
            raise ValueError(f"資料不符合限制：{e}") from None
        return values[pk], action

    def dim_delete(self, kind, key):
        meta = self._meta(kind)
        try:
            cur = self.conn.execute(f"DELETE FROM {meta['table']} WHERE {meta['pk']} = ?", (key,))
            self.conn.commit()
        except sqlite3.IntegrityError:
            self.conn.rollback()
            hint = "，可改為停用（is_active）" if kind == "shift" else ""
            raise ValueError(f"{key} 仍被其他資料參照，無法刪除{hint}") from None
        if cur.rowcount == 0:
            raise ValueError(f"找不到 {key}")
