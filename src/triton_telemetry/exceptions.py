"""Excepciones semanticas del ecosistema TritonMonitor."""


class TritonError(Exception):
    """Excepcion base para todos los fallos del ecosistema TritonMonitor."""


class ProviderTimeoutError(TritonError):
    """Lanzada cuando un proveedor de nube supera el tiempo de espera (Timeout) establecido."""


class CorruptedPayloadError(TritonError):
    """Lanzada cuando la respuesta recibida del proveedor cloud esta corrupta o devuelve un estatus HTTP fallido."""


class NetworkPeeringError(TritonError):
    """Lanzada cuando existen fallos de resolucion de DNS, ruteo o perdida de conectividad fisica."""
