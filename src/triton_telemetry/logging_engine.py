"""Pipeline de observabilidad: formateador JSON recursivo y logging no bloqueante por cola.

Alternativas profesionales no implementadas: structlog, python-json-logger.
"""

import gzip
import json
import logging
import logging.config
import logging.handlers
import os
import queue
import shutil
from datetime import datetime, timezone


def gzip_namer(name: str) -> str:
    """Agrega la extension .gz al nombre del archivo de backup."""
    return name + ".gz"


def gzip_rotator(source: str, dest: str):
    """Comprime el archivo rotado a .gz y elimina el plano residual."""
    with open(source, "rb") as f_in, gzip.open(dest, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(source)


class AsyncJSONFormatter(logging.Formatter):
    """Serializa cada LogRecord a JSON, expandiendo ExceptionGroups de forma recursiva."""
    def _serialize_exception(self, exc: BaseException) -> dict:
        exc_data = {
            "class": exc.__class__.__name__,
            "message": str(exc),
            "notes": list(getattr(exc, "__notes__", []) or []),
        }

        # Un ExceptionGroup puede tener ademas una causa encadenada, se serializan ambas ramas
        if isinstance(exc, ExceptionGroup):
            exc_data["nested_exceptions"] = [
                self._serialize_exception(nested) for nested in exc.exceptions
            ]
        if exc.__cause__ is not None:
            exc_data["cause"] = self._serialize_exception(exc.__cause__)

        return exc_data

    def format(self, record: logging.LogRecord) -> str:
        dt_utc = datetime.fromtimestamp(record.created, tz=timezone.utc)

        log_payload = {
            "timestamp": dt_utc.isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "process": record.process,
            "thread_name": record.threadName,
            "async_task": getattr(record, "taskName", "None"),
            "filename": record.filename,
            "line": record.lineno,
        }

        if record.exc_info:
            exc_value = record.exc_info[1]
            if exc_value:
                log_payload["exception_tree"] = self._serialize_exception(exc_value)
                log_payload["stack_trace"] = self.formatException(record.exc_info)

        reserved_fields = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in reserved_fields and not key.startswith("_"):
                log_payload[key] = value

        return json.dumps(log_payload, ensure_ascii=False, default=str)


class TritonQueueHandler(logging.handlers.QueueHandler):
    """Encola el registro sin pre-formatearlo, conservando exc_info para el formateador del listener."""

    def prepare(self, record):
        return record


def setup_triton_logging(log_filename: str = "triton_services.log") -> logging.Logger:
    """Configura el logging con dictConfig y desacopla la escritura de disco con QueueHandler/QueueListener."""
    logging_schema = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json_structured": {"()": AsyncJSONFormatter},
            "console_clean": {
                "format": "%(asctime)s [%(levelname)s] %(message)s",
                "datefmt": "%H:%M:%S",
            },
        },
        "handlers": {
            "stdout_console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "console_clean",
                "stream": "ext://sys.stdout",
            },
            "rotating_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "json_structured",
                "filename": log_filename,
                "maxBytes": 2 * 1024 * 1024,
                "backupCount": 3,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "triton_monitor": {
                "level": "DEBUG",
                "handlers": ["stdout_console", "rotating_file"],
                "propagate": False,
            }
        },
    }

    logging.config.dictConfig(logging_schema)
    app_logger = logging.getLogger("triton_monitor")

    file_handler = next(
        (h for h in app_logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)),
        None,
    )
    if file_handler:
        file_handler.namer = gzip_namer
        file_handler.rotator = gzip_rotator

    # El logger solo encola eventos; el hilo del listener hace la escritura fisica
    log_queue = queue.Queue(-1)
    queue_handler = TritonQueueHandler(log_queue)
    listener = logging.handlers.QueueListener(
        log_queue, *app_logger.handlers, respect_handler_level=True
    )

    app_logger.handlers = [queue_handler]
    listener.start()
    app_logger.listener = listener

    return app_logger
