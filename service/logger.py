"""
Common structured logger.

Every service calls ``get_logger("service_name")`` to get a logger instance
that produces one JSON object per line.  The ``service`` field in each log
entry identifies the originating component for easy filtering.
"""
import json
import logging
import sys


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "service": getattr(record, "service_name", record.name),
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)
    _configured = True


def get_logger(service_name: str) -> logging.Logger:
    """Return a named logger for a specific service component."""
    _configure_root()
    logger = logging.getLogger(f"service.{service_name}")

    original_make_record = logger.makeRecord

    def _make_record(
        name, level, fn, lno, msg, args, exc_info,
        func=None, extra=None, sinfo=None,
    ):
        if extra is None:
            extra = {}
        extra.setdefault("service_name", service_name)
        return original_make_record(
            name, level, fn, lno, msg, args, exc_info, func, extra, sinfo,
        )

    logger.makeRecord = _make_record  # type: ignore[assignment]
    return logger
