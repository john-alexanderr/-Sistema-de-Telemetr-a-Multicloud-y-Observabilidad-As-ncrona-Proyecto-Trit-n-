"""Motor de telemetria: consultas HTTP concurrentes con httpx y asyncio.TaskGroup.

Alternativas profesionales no implementadas: aiohttp como cliente, tenacity para reintentos.
"""

import asyncio
import json
import logging
import os

import httpx

from .exceptions import CorruptedPayloadError, NetworkPeeringError, ProviderTimeoutError

logger = logging.getLogger("triton_monitor")

PROVIDER_ENDPOINTS = {
    "AWS": "https://jsonplaceholder.typicode.com/posts/1",
    "Azure": "https://jsonplaceholder.typicode.com/posts/2",
    "GCP": "https://jsonplaceholder.typicode.com/posts/3",
}

CHAOS_ENDPOINTS = {
    "TIMEOUT_TRIGGER": "https://httpbin.org/delay/3",
    "BAD_GATEWAY_TRIGGER": "https://httpbin.org/status/504",
    "CORRUPTED_TRIGGER": "https://httpbin.org/xml",
}

# Permite a la suite de caos redirigir las consultas hacia un host inexistente (prueba de DNS)
BASE_URL_OVERRIDE = os.environ.get("TRITON_BASE_URL")


async def query_provider_telemetry(provider: str, timeout: float, use_chaos: bool = False) -> dict:
    """Consulta la telemetria de un proveedor y mapea los errores nativos de httpx a errores semanticos."""
    if BASE_URL_OVERRIDE:
        url = f"{BASE_URL_OVERRIDE}/{provider.lower()}"
    elif use_chaos:
        if provider == "AWS":
            url = CHAOS_ENDPOINTS["TIMEOUT_TRIGGER"]
        elif provider == "Azure":
            url = CHAOS_ENDPOINTS["BAD_GATEWAY_TRIGGER"]
        else:
            url = CHAOS_ENDPOINTS["CORRUPTED_TRIGGER"]
    else:
        url = PROVIDER_ENDPOINTS[provider]

    logger.debug(f"Peticion iniciada hacia {provider} en {url}", extra={"provider": provider, "target_url": url})

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=timeout)
            response.raise_for_status()
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError) as err:
                c_err = CorruptedPayloadError(f"El proveedor {provider} devolvio un payload corrupto o no serializable.")
                c_err.add_note(f"Provider_ID: {provider}")
                c_err.add_note(f"Target_Endpoint: {url}")
                raise c_err from err

            logger.info(
                f"Telemetria recibida de {provider}",
                extra={"provider": provider, "status_code": response.status_code},
            )
            return {
                "provider": provider,
                "status": "NOMINAL",
                "latency_sec": response.elapsed.total_seconds(),
                "payload_id": data.get("id", -1),
            }

        except httpx.TimeoutException as err:
            t_err = ProviderTimeoutError(f"Se agoto el tiempo de espera ({timeout}s) al conectar con {provider}.")
            t_err.add_note(f"Provider_ID: {provider}")
            t_err.add_note(f"Requested_Timeout_Limit: {timeout}s")
            t_err.add_note(f"Target_Endpoint: {url}")
            raise t_err from err

        except httpx.HTTPStatusError as err:
            c_err = CorruptedPayloadError(
                f"Estatus HTTP no esperado recibido de {provider}: {err.response.status_code}."
            )
            c_err.add_note(f"Provider_ID: {provider}")
            c_err.add_note(f"HTTP_Status_Code: {err.response.status_code}")
            c_err.add_note(f"HTTP_Method: {err.request.method}")
            raise c_err from err

        except httpx.RequestError as err:
            n_err = NetworkPeeringError(f"Error critico de transporte de red al intentar alcanzar {provider}.")
            n_err.add_note(f"Provider_ID: {provider}")
            n_err.add_note(f"Network_Error_Type: {type(err).__name__}")
            n_err.add_note(f"Target_Endpoint: {url}")
            raise n_err from err


async def scan_all_providers(providers: list[str], timeout: float, use_chaos: bool = False) -> list[dict]:
    """Orquesta las consultas paralelas dentro de un asyncio.TaskGroup."""
    tasks = []
    results = []

    async with asyncio.TaskGroup() as tg:
        for provider in providers:
            task = tg.create_task(
                query_provider_telemetry(provider, timeout, use_chaos),
                name=f"Task-{provider}",
            )
            tasks.append(task)

    for task in tasks:
        results.append(task.result())

    return results
