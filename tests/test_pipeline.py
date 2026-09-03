"""Test de punta a punta del pipeline: el arbol de excepciones llega intacto al archivo JSON."""

import json

from triton_telemetry.exceptions import ProviderTimeoutError
from triton_telemetry.logging_engine import setup_triton_logging


def test_exception_tree_sobrevive_la_cola(tmp_path):
    logger = setup_triton_logging(str(tmp_path / "triton_test.log"))
    try:
        try:
            raise ProviderTimeoutError("timeout simulado")
        except ProviderTimeoutError as err:
            err.add_note("Provider_ID: AWS")
            logger.error("fallo de prueba", exc_info=err)
    finally:
        logger.listener.stop()

    lineas = (tmp_path / "triton_test.log").read_text(encoding="utf-8").splitlines()
    eventos = [json.loads(linea) for linea in lineas]
    evento_error = next(e for e in eventos if e["level"] == "ERROR")

    assert evento_error["exception_tree"]["class"] == "ProviderTimeoutError"
    assert evento_error["exception_tree"]["notes"] == ["Provider_ID: AWS"]
    assert evento_error["timestamp"].endswith("Z")
