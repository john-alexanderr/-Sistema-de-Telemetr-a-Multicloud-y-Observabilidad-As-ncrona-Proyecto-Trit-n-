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
    """Agrega .gz al nombre del backup durante la rotacion."""
    return name + ".gz"


def gzip_rotator(source: str, dest: str):
    """Comprime el backup recien rotado a .gz y borra el plano original."""
    with open(source, "rb") as f_in, gzip.open(dest, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(source)


class AsyncJSONFormatter(logging.Formatter):
    """Serializa cada LogRecord como una linea JSON (una linea = un evento).

    Guarda timestamp ISO 8601 UTC, proceso, hilo, tarea de asyncio, los
    metadatos extra y el arbol completo de excepciones: grupos anidados,
    causas encadenadas y notas, sin truncar nada.
    """

    def _serialize_exception(self, exc: BaseException) -> dict:
        """Traduce una excepcion a dict, entrando en grupos y causas recursivamente."""
        exc_data = {
            "class": exc.__class__.__name__,
            "message": str(exc),
            "notes": list(getattr(exc, "__notes__", []) or []),
        }

        if isinstance(exc, ExceptionGroup):
            exc_data["nested_exceptions"] = [
                self._serialize_exception(nested) for nested in exc.exceptions
            ]
        if exc.__cause__ is not None:
            exc_data["cause"] = self._serialize_exception(exc.__cause__)

        return exc_data

    def format(self, record: logging.LogRecord) -> str:
        """Arma el expediente JSON del evento; corre en el hilo del listener."""
        dt_utc = datetime.fromtimestamp(record.created, tz=timezone.utc)

        log_payload = {
            "timestamp": dt_utc.isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "process": record.process,
            "thread_name": record.threadName,
            "async_task": getattr(record, "taskName", None),
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
    """QueueHandler que encola el registro sin re-formatearlo.

    El prepare por defecto destruye record.exc_info, y sin exc_info el arbol
    de excepciones no sobrevive el viaje por la cola. Aca el registro pasa
    intacto y el formateo real lo hace el listener del otro lado.
    """

    def prepare(self, record):
        """Devuelve el registro tal como llego."""
        return record


def setup_triton_logging(log_filename: str = "triton_services.log") -> logging.Logger:
    """Arma el pipeline con dictConfig y lo desacopla con una cola.

    El logger solo encola via QueueHandler (microsegundos, el event loop
    nunca se bloquea) y un QueueListener en un hilo aparte hace la E/S real:
    consola mas el archivo rotativo de 2 MB con backups comprimidos a gzip.
    El listener queda colgado en logger.listener para apagarlo en el finally.
    """
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

    log_queue = queue.Queue(-1)
    queue_handler = TritonQueueHandler(log_queue)
    listener = logging.handlers.QueueListener(
        log_queue, *app_logger.handlers, respect_handler_level=True
    )

    app_logger.handlers = [queue_handler]
    listener.start()
    app_logger.listener = listener

    return app_logger


def set_console_level(logger: logging.Logger, level: int) -> None:
    """Cambia en caliente el nivel del handler de consola.

    Ojo que el handler vive dentro del listener, no en el logger (que solo
    tiene el QueueHandler); funciona porque el listener se creo con
    respect_handler_level=True.
    """
    listener = getattr(logger, "listener", None)
    if listener is None:
        return

    for handler in listener.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            handler.setLevel(level)
