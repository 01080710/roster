"""
集中管理可重複使用 / 可調整的參數。

標註「環境變數」的項目可在啟動前用環境變數覆寫，例如（PowerShell）：
    $env:ROSTER_PORT = "8000"; py -3.12 main.py
"""
import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# =====================================================================
# 執行環境
# =====================================================================
DB_PATH = os.environ.get("ROSTER_DB_PATH", os.path.join(BASE_DIR, "roster.db"))   # 環境變數
HOST = os.environ.get("ROSTER_HOST", "127.0.0.1")                                 # 環境變數
PORT = int(os.environ.get("ROSTER_PORT", "5000"))                                 # 環境變數
DEBUG = _env_bool("ROSTER_DEBUG", True)                                           # 環境變數

# =====================================================================
# 排班規則
# =====================================================================
MIN_REST_HOURS = 11          # 兩班之間最少休息時數
MAX_RANGE_DAYS = 62          # 一次最多提交幾天
OT_FULL_DAY_HOURS = 8        # 標記加班時，工時達到幾小時算 1 天（未達算 0.5 天）

# =====================================================================
# 代碼與選項（資料表 CHECK 限制、下拉選單共用）
# =====================================================================
OFFICE_TZ = {
    "TW": "Asia/Taipei",
    "MY": "Asia/Kuala_Lumpur",
    "PH": "Asia/Manila",
    "MA": "Africa/Casablanca",
    "VN": "Asia/Ho_Chi_Minh",
}
REST_PATTERN = {             # 休息模式 → 休息日（ISO weekday：1 = 週一 … 7 = 週日）
    "SAT_SUN": (6, 7), "SUN_MON": (7, 1), "MON_TUE": (1, 2), "TUE_WED": (2, 3),
    "WED_THU": (3, 4), "THU_FRI": (4, 5), "FRI_SAT": (5, 6),
}
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CATEGORY_LABEL = {
    "SHIFT": "上班班別", "OT": "加班", "OFF": "休息 / 國定假日",
    "LEAVE": "請假", "ACTIVITY": "公務活動",
}
STATUS_GROUPS = ["Work", "Rest", "Leave", "Duty (off-site)"]
SHIFT_TYPES = ["Morning", "Night", "Midnight", "N/A"]
DAY_PORTIONS = ["FD", "H1", "H2", "QT", "PT"]
TEAMS = ["AO", "DW", "AO_DW"]
DAY_TYPES = ["Work Day", "Rest Day", "PH"]
APPROVAL_STATUSES = ["Approved", "Pending", "Rejected"]

# 年度總覽的狀態分類與圖例（順序即圖例順序）
SITUATION_LABELS = [("SHIFT", "上班"), ("LEAVE", "請假"), ("OT", "加班"),
                    ("OFF", "休息 / 國定假日"), ("ACTIVITY", "公務活動")]

# =====================================================================
# 帳號與權限
# =====================================================================
PERMISSIONS = ["USER_VIEW", "USER_CREATE", "USER_EDIT", "USER_DELETE"]
AGENT_ROLE = "Agent"
AGENT_PERMISSIONS = ["USER_VIEW", "USER_CREATE"]     # Agent 預設權限；其他角色預設 PERMISSIONS 全部
PASSWORD_MIN_LENGTH = 8


# =====================================================================
# JWT 驗證
# =====================================================================
def _load_secret_key():
    """優先用環境變數 ROSTER_SECRET_KEY；否則在專案資料夾產生 .secret_key 並沿用（重啟後 token 仍有效）。"""
    if os.environ.get("ROSTER_SECRET_KEY"):
        return os.environ["ROSTER_SECRET_KEY"]
    path = os.path.join(BASE_DIR, ".secret_key")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


JWT_SECRET_KEY = _load_secret_key()                                     # 環境變數 ROSTER_SECRET_KEY
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 30                                                 # 登入有效時間（分鐘）
JWT_COOKIE_NAME = "access_token"
JWT_COOKIE_SECURE = _env_bool("ROSTER_COOKIE_SECURE", False)            # 環境變數；走 HTTPS 時設 true
JWT_COOKIE_SAMESITE = "Lax"

# =====================================================================
# 介面
# =====================================================================
RECENT_ROSTER_LIMIT = 50     # 「查詢與修改」最多顯示筆數
PIVOT_YEARS_BEFORE = 2       # 年度總覽的年份選單：今年往前幾年
PIVOT_YEARS_AFTER = 2        # 年度總覽的年份選單：今年往後幾年

# 維度表頁面設定
# pk_mode：manual = 新增時必填；auto = 留空自動編號；derived = 由其他欄位組成
DIM_TABLES = {
    "shift": {
        "table": "dim_shift_code", "pk": "shift_code", "pk_mode": "manual", "label": "班別",
        "order": "sort_order, shift_code",
        "list_cols": ["shift_code", "roster_display", "shift_name", "category", "status_group",
                      "start_time", "end_time", "break_minutes", "day_portion", "is_active", "updated_at"],
    },
    "employee": {
        "table": "dim_employee", "pk": "employee_id", "pk_mode": "auto", "label": "員工",
        "order": "office_code, full_name",
        "list_cols": ["employee_id", "full_name", "email", "office_code", "team", "role",
                      "rest_pattern_code", "default_shift_code", "hire_date", "termination_date",
                      "permission", "updated_at"],
    },
    "holiday": {
        "table": "dim_holiday", "pk": "holiday_id", "pk_mode": "derived", "label": "假日",
        "order": "holiday_date DESC, calendar_code",
        "list_cols": ["holiday_id", "calendar_code", "holiday_date", "holiday_name",
                      "holiday_group", "is_substitute", "updated_at"],
    },
}
# 維度表編輯頁的下拉選項（欄位名稱 → 可選值）
FIELD_CHOICES = {
    "category": list(CATEGORY_LABEL),
    "status_group": STATUS_GROUPS,
    "shift_type": SHIFT_TYPES,
    "day_portion": DAY_PORTIONS,
    "office_code": list(OFFICE_TZ),
    "calendar_code": list(OFFICE_TZ),
    "team": TEAMS,
    "rest_pattern_code": list(REST_PATTERN),
}
