"""Tests del formateador JSON: metadatos obligatorios y serializacion recursiva."""

import json
import logging

from triton_telemetry.exceptions import CorruptedPayloadError, ProviderTimeoutError
from triton_telemetry.logging_engine import AsyncJSONFormatter


def _build_record(exc=None, extra=None):
    record = logging.LogRecord(
        name="triton_monitor",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="prueba de formato",
        args=(),
        exc_info=(type(exc), exc, exc.__traceback__) if exc else None,
    )
    if extra:
        for key, value in extra.items():
            setattr(record, key, value)
    return record


def test_metadata_iso8601_utc():
    payload = json.loads(AsyncJSONFormatter().format(_build_record()))
    assert payload["timestamp"].endswith("Z")
    assert payload["process"]
    assert payload["thread_name"]
    assert "async_task" in payload


def test_exception_group_serializado_de_forma_recursiva():
    try:
        try:
            raise ProviderTimeoutError("timeout AWS")
        except ProviderTimeoutError as base:
            derived = CorruptedPayloadError("payload corrupto Azure")
            raise ExceptionGroup("colapso multicloud", [base, derived]) from base
    except ExceptionGroup as group:
        record = _build_record(exc=group)

    payload = json.loads(AsyncJSONFormatter().format(record))
    tree = payload["exception_tree"]

    assert tree["class"] == "ExceptionGroup"
    assert len(tree["nested_exceptions"]) == 2
    assert tree["cause"]["class"] == "ProviderTimeoutError"
    assert payload["stack_trace"]


def test_excepcion_con_notas_y_causa():
    try:
        try:
            raise ValueError("causa raiz httpx")
        except ValueError as causa:
            err = ProviderTimeoutError("timeout superado")
            err.add_note("Target_Endpoint: https://httpbin.org/delay/3")
            raise err from causa
    except ProviderTimeoutError as err:
        record = _build_record(exc=err)

    payload = json.loads(AsyncJSONFormatter().format(record))
    tree = payload["exception_tree"]

    assert tree["notes"] == ["Target_Endpoint: https://httpbin.org/delay/3"]
    assert tree["cause"]["class"] == "ValueError"


def test_metadatos_extra():
    payload = json.loads(AsyncJSONFormatter().format(_build_record(extra={"provider": "AWS", "status_code": 200})))
    assert payload["provider"] == "AWS"
    assert payload["status_code"] == 200
