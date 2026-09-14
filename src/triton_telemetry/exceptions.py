class TritonError(Exception):
    """Error base del ecosistema Triton.

    Hereda de Exception y no de BaseException a proposito: capturar
    BaseException secuestraria senales del sistema como Ctrl+C.
    """


class ProviderTimeoutError(TritonError):
    """Un proveedor cloud no respondio dentro del timeout configurado."""


class CorruptedPayloadError(TritonError):
    """La respuesta llego pero no sirve: estatus HTTP fallido o payload no serializable."""


class NetworkPeeringError(TritonError):
    """Fallo de transporte: DNS caido, host inalcanzable o conexion rechazada."""
