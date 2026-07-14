import json
import logging
import re
import threading
import time
from datetime import datetime, timezone

from django.conf import settings


SENSITIVE = re.compile(
    r"(?i)(password|passwd|secret|token|authorization|cookie)(\s*[:=]\s*)([^\s,;]+)"
)


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record):
        message = SENSITIVE.sub(r"\1\2[REDACTED]", record.getMessage())
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        if record.exc_info:
            payload["exception"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=True)


class RetentionCleanupMiddleware:
    _lock = threading.Lock()
    _last_run = 0.0

    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("home_ai.retention")

    def __call__(self, request):
        interval = settings.DATA_RETENTION_CLEANUP_INTERVAL_SECONDS
        now = time.monotonic()
        if now - self.__class__._last_run >= interval and self.__class__._lock.acquire(
            blocking=False
        ):
            try:
                if now - self.__class__._last_run >= interval:
                    from abbreviation_tool.storage import cleanup_expired

                    removed = cleanup_expired()
                    self.__class__._last_run = now
                    if removed:
                        self.logger.info(
                            "Expired processing resources removed count=%s", removed
                        )
            except Exception:
                self.logger.exception("Retention cleanup failed")
            finally:
                self.__class__._lock.release()
        return self.get_response(request)
