from triton_telemetry.exceptions import (
    CorruptedPayloadError,
    NetworkPeeringError,
    ProviderTimeoutError,
    TritonError,
)


def test_herencia_exception_y_no_baseexception():
    for exc_class in (TritonError, ProviderTimeoutError, CorruptedPayloadError, NetworkPeeringError):
        assert issubclass(exc_class, Exception)
        assert exc_class.__bases__ != (BaseException,)


def test_subclases_de_triton_error():
    for exc_class in (ProviderTimeoutError, CorruptedPayloadError, NetworkPeeringError):
        assert issubclass(exc_class, TritonError)


def test_add_note_conserva_el_contexto():
    err = ProviderTimeoutError("timeout superado")
    err.add_note("Provider_ID: AWS")
    err.add_note("Requested_Timeout_Limit: 1.0s")
    assert err.__notes__ == ["Provider_ID: AWS", "Requested_Timeout_Limit: 1.0s"]
