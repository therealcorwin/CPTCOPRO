import os
from typing import Any

try:
    from loguru import logger  # type: ignore

    _HAS_LOGURU = True
except Exception:
    _HAS_LOGURU = False
    # Fallback to standard logging with a minimal shim exposing the methods
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
    )

    class _StdLoggerShim:
        def __init__(self, lg: logging.Logger):
            self._lg = lg

        def add(self, *args, **kwargs):
            # no-op for compatibility
            return None

        def remove(self, *args, **kwargs):
            # no-op for compatibility
            return None

        def debug(self, *args, **kwargs):
            self._lg.debug(*args, **kwargs)

        def info(self, *args, **kwargs):
            self._lg.info(*args, **kwargs)

        def warning(self, *args, **kwargs):
            self._lg.warning(*args, **kwargs)

        def error(self, *args, **kwargs):
            self._lg.error(*args, **kwargs)

        def bind(self, **extra):
            # Return self; extra is ignored for the shim
            return self

    logger = _StdLoggerShim(logging.getLogger("ctpcopro"))

# Configure log level from environment (default INFO)
LOG_LEVEL = os.getenv("CTPCOPRO_LOG_LEVEL", "INFO").upper()

if _HAS_LOGURU:
    # Remove default handlers and add a safe formatter that tolerates missing extra fields
    logger.remove()

    def _format_record(record: Any) -> str:
        """Return a formatted log line from a Loguru record.

        Accept either the mapping-style record provided by Loguru or an object-like
        record. Be defensive about missing attributes.
        """
        # time handling: record can be a dict-like or an object
        time = None
        if isinstance(record, dict):
            time = record.get("time")
        else:
            time = getattr(record, "time", None)

        if time is not None and hasattr(time, "strftime"):
            time_str = time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = str(time)

        # level: support dict-style record where 'level' can be a mapping or an object
        level = "LEVEL"
        if isinstance(record, dict):
            lv = record.get("level", None)
            if isinstance(lv, dict):
                level = lv.get("name", "LEVEL")
            else:
                # lv may be a Loguru RecordLevel object or similar
                level = getattr(lv, "name", None) or (
                    str(lv) if lv is not None else "LEVEL"
                )
        else:
            level = getattr(getattr(record, "level", None), "name", "LEVEL")

        # extra
        if isinstance(record, dict):
            extra = record.get("extra", {}) or {}
        else:
            extra = getattr(record, "extra", {}) or {}

        # extra may not be a plain dict; try to access like a mapping then attr
        type_log = None
        if isinstance(extra, dict):
            type_log = extra.get("type_log")
        else:
            type_log = (
                getattr(extra, "get", None)
                and extra.get("type_log")
                or getattr(extra, "type_log", None)
            )
        if not type_log:
            type_log = "MAIN"

        # message
        if isinstance(record, dict):
            message = record.get("message", "")
        else:
            message = getattr(record, "message", "")

        return f"{time_str} | {level} | {type_log} | {message}\n"

    # Console sink (prints without adding extra newline)
    logger.add(
        sink=lambda msg: print(msg, end=""), level=LOG_LEVEL, format=_format_record
    )

    # File sink (rotating by size) - Utiliser le chemin portable si disponible
    log_file = os.getenv("CTPCOPRO_LOG_FILE", None)
    if log_file is None:
        try:
            from cptcopro.utils.paths import get_log_path
            log_file = str(get_log_path("ctpcopro.log"))
        except Exception:
            log_file = "ctpcopro.log"
    logger.add(log_file, rotation="10 MB", level=LOG_LEVEL, format=_format_record)

    logger.debug(f"Logger initialisé (level={LOG_LEVEL}, file={log_file})")
else:
    # Using stdlib logging shim — honor CTPCOPRO_LOG_FILE if set by configuring a FileHandler
    log_file = os.getenv("CTPCOPRO_LOG_FILE", None)
    if log_file is None:
        try:
            from cptcopro.utils.paths import get_log_path
            log_file = str(get_log_path("ctpcopro.log"))
        except ImportError:
            log_file = None
    if log_file:
        try:
            import logging

            fh = logging.FileHandler(log_file)
            fh.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
            )
            logging.getLogger("ctpcopro").addHandler(fh)
            logging.getLogger("ctpcopro").setLevel(
                getattr(logging, LOG_LEVEL, logging.INFO)
            )
        except Exception:
            pass
    logger.info(f"Stdlib logger initialisé (level={LOG_LEVEL}, file={log_file})")
