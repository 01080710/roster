"""JSON 格式的日誌：同時輸出到終端機，並依日期 / 使用者 / 面向寫入檔案。

    logs/2026-10-09/amy@example.com/behavior.log    使用者行為
    logs/2026-10-09/amy@example.com/debug.log       系統執行
    logs/2026-10-09/_system/debug.log               沒有使用者的紀錄

每一行是一筆 JSON。寫檔位置由紀錄上的 user 與 channel 欄位決定（預設 _system / debug）：
    log.info("登入", extra={"channel": "behavior", "user": "amy@example.com", "action": "login"})
"""
import datetime as dt
import json
import logging
import os
import re
import shutil
import sys

SYSTEM_USER = "_system"
CHANNELS = ("behavior", "debug")


class JsonFormatter(logging.Formatter):
    RESERVED_ATTRS = {
        "args", "msg", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno",
        "funcName", "created", "msecs", "relativeCreated", "thread",
        "threadName", "processName", "process", "name", "taskName", "message", "asctime",
        "channel",          # 只用來決定寫到哪個檔案
    }

    @staticmethod
    def _status(record):
        """WARNING / ERROR 不沿用預設的 ok。"""
        if record.levelno >= logging.ERROR:
            return "error"
        if record.levelno >= logging.WARNING:
            return "warning"
        return getattr(record, "status", "unknown")

    def format(self, record):
        # basic log structure
        log_record = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "service": getattr(record, "service", "unknown"),
            "logger": record.name,
            "stage": getattr(record, "stage", "unknown"),
            "status": self._status(record),
            "message": record.getMessage(),
        }

        # mange custom attributes (exclude reserved ones and empty values)
        for key, value in record.__dict__.items():
            if key not in log_record and key not in self.RESERVED_ATTRS:
                if value not in (None, "", []):
                    log_record[key] = value

        # logger.exception(...) 或 exc_info=... 時附上 traceback
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # date、sqlite3.Row 等無法直接轉 JSON 的值改成字串，不讓寫 log 本身出錯
        return json.dumps(log_record, ensure_ascii=False, default=str)


class ContextLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})

        # merge context with log-specific extra (log-specific takes precedence)
        merged = {**self.extra, **extra}
        kwargs["extra"] = merged

        return msg, kwargs


def safe_folder_name(user):
    """email 當資料夾名稱：轉小寫，檔名不允許的字元換成 _。"""
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", str(user or SYSTEM_USER).strip().lower())
    return name.strip(".") or SYSTEM_USER


class UserDailyFileHandler(logging.Handler):
    """依紀錄的日期、user、channel 寫到 <log_dir>/YYYY-MM-DD/<user>/<channel>.log。
    開過的檔案會沿用；換日時關掉前一天的檔案。"""

    def __init__(self, log_dir):
        super().__init__()
        self.log_dir = log_dir
        self._day = None
        self._streams = {}

    def _stream(self, record):
        day = dt.datetime.fromtimestamp(record.created).strftime("%Y-%m-%d")
        if day != self._day:
            self._close_streams()
            self._day = day
        channel = getattr(record, "channel", "debug")
        channel = channel if channel in CHANNELS else "debug"
        folder = os.path.join(self.log_dir, day, safe_folder_name(getattr(record, "user", None)))
        path = os.path.join(folder, f"{channel}.log")
        if path not in self._streams:
            os.makedirs(folder, exist_ok=True)
            self._streams[path] = open(path, "a", encoding="utf-8")
        return self._streams[path]

    def emit(self, record):
        try:
            stream = self._stream(record)
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)

    def _close_streams(self):
        for stream in self._streams.values():
            stream.close()
        self._streams = {}

    def close(self):
        self.acquire()
        try:
            self._close_streams()
        finally:
            self.release()
        super().close()


def get_logger(
    service: str = "etl",
    logger_name: str = "etl_logger",
    stage: str = "local",
    log_dir: str | None = None,
):

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # FileHandler 也是 StreamHandler 的子類別，所以用 type() 精確比對
    if not any(type(h) is logging.StreamHandler for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

    if log_dir and not any(isinstance(h, UserDailyFileHandler) for h in logger.handlers):
        handler = UserDailyFileHandler(log_dir)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

    return ContextLoggerAdapter(
        logger,
        {
            "service": service,
            "stage": stage,
            "status": "ok",
        },
    )


def cleanup_old_logs(log_dir, keep_days):
    """刪除超過 keep_days 天的日期資料夾（只動 YYYY-MM-DD 格式的資料夾），回傳刪掉的資料夾名稱。"""
    if not os.path.isdir(log_dir):
        return []
    cutoff = (dt.date.today() - dt.timedelta(days=keep_days - 1)).isoformat()
    removed = []
    for name in sorted(os.listdir(log_dir)):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", name) and name < cutoff:
            shutil.rmtree(os.path.join(log_dir, name), ignore_errors=True)
            removed.append(name)
    return removed
