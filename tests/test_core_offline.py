import asyncio
from datetime import timedelta

import httpx
import pytest

from triton_telemetry import core
from triton_telemetry.exceptions import CorruptedPayloadError, ProviderTimeoutError


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    holder = {"handler": None}
    real_client = httpx.AsyncClient

    def handler_de_prueba(request):
        response = holder["handler"](request)
        # MockTransport no cierra la respuesta, se fija elapsed manualmente
        response.elapsed = timedelta(0)
        return response

    def patched(**kwargs):
        return real_client(transport=httpx.MockTransport(handler_de_prueba))

    monkeypatch.setattr(core.httpx, "AsyncClient", patched)
    return lambda handler: holder.update(handler=handler)


def _run(coro):
    return asyncio.run(coro)


def test_nominal(_patch_client):
    _patch_client(lambda request: httpx.Response(200, json={"id": 1}))
    result = _run(core.query_provider_telemetry("AWS", timeout=2.0))
    assert result["provider"] == "AWS"
    assert result["status"] == "NOMINAL"
    assert result["payload_id"] == 1


def test_timeout_se_mapea_a_provider_timeout(_patch_client):
    # El timeout de httpx depende de I/O real; en el mock se inyecta la excepcion directamente
    def timeout_handler(request):
        raise httpx.ReadTimeout("Latencia simulada superior al limite", request=request)

    _patch_client(timeout_handler)
    with pytest.raises(ProviderTimeoutError) as excinfo:
        _run(core.query_provider_telemetry("AWS", timeout=0.5))
    assert "Provider_ID: AWS" in excinfo.value.__notes__


def test_estatus_504_se_mapea_a_corrupted_payload(_patch_client):
    _patch_client(lambda request: httpx.Response(504))
    with pytest.raises(CorruptedPayloadError) as excinfo:
        _run(core.query_provider_telemetry("Azure", timeout=2.0))
    assert any("504" in note for note in excinfo.value.__notes__)


def test_payload_xml_se_mapea_a_corrupted_payload(_patch_client):
    _patch_client(lambda request: httpx.Response(200, content=b"<xml>oops</xml>"))
    with pytest.raises(CorruptedPayloadError):
        _run(core.query_provider_telemetry("GCP", timeout=2.0))


def test_scan_agrupa_fallos_en_exception_group(_patch_client):
    def handler(request):
        if str(request.url).endswith("posts/1"):
            return httpx.Response(200, json={"id": 1})
        return httpx.Response(504)

    _patch_client(handler)
    with pytest.raises(ExceptionGroup) as excinfo:
        _run(core.scan_all_providers(["AWS", "Azure"], timeout=2.0))
    assert len(excinfo.value.exceptions) == 1


def test_scan_conserva_fallos_de_todos_los_proveedores(_patch_client):
    _patch_client(lambda request: httpx.Response(504, request=request))

    with pytest.raises(ExceptionGroup) as excinfo:
        _run(core.scan_all_providers(["AWS", "Azure", "GCP"], timeout=2.0))

    assert len(excinfo.value.exceptions) == 3
    assert all(isinstance(error, CorruptedPayloadError) for error in excinfo.value.exceptions)
