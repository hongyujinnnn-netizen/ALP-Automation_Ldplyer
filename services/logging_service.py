from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import AppPaths


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for structured application logs."""

    RESERVED_ATTRS = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


class AppLogger:
    """Structured logger facade used by UI and services."""

    LEVEL_MAP = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "SUCCESS": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }

    def __init__(self, paths: AppPaths, logger_name: str = "ldmanager") -> None:
        self.paths = paths
        self.paths.ensure_runtime_dirs()
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self._configure_handlers(self.paths.logs_dir / "app.jsonl")

    def log(self, level: str, message: str, **context: Any) -> None:
        normalized_level = level.upper()
        log_level = self.LEVEL_MAP.get(normalized_level, logging.INFO)
        extra = {"ui_level": normalized_level}
        extra.update(context)
        self.logger.log(log_level, message, extra=extra)

    def _configure_handlers(self, log_path: Path) -> None:
        existing_handler = next(
            (
                handler
                for handler in self.logger.handlers
                if isinstance(handler, logging.FileHandler)
                and Path(getattr(handler, "baseFilename", "")) == log_path
            ),
            None,
        )
        if existing_handler is not None:
            return

        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)

    def close(self) -> None:
        for handler in list(self.logger.handlers):
            handler.flush()
            handler.close()
            self.logger.removeHandler(handler)
