"""Punto de entrada CLI de TritonMonitor.

Alternativa profesional no implementada: typer sobre argparse.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from triton_telemetry import (
    CorruptedPayloadError,
    NetworkPeeringError,
    ProviderTimeoutError,
    TritonError,
    parse_cluster_id,
    parse_timeout,
    scan_all_providers,
    setup_triton_logging,
)

logger = setup_triton_logging()


def build_cli_parser() -> argparse.ArgumentParser:
    """Configura el analizador CLI con los validadores de frontera y restricciones de dominio."""
    parser = argparse.ArgumentParser(
        prog="TritonMonitor",
        description="Consola de Telemetria Multicloud y Observabilidad Asincrona (PROYECTO TRITON).",
    )

    parser.add_argument(
        "proveedores",
        nargs="+",
        choices=["AWS", "Azure", "GCP"],
        help="Lista de identificadores de los proveedores cloud a monitorear.",
    )

    parser.add_argument(
        "-c", "--cluster-id",
        type=parse_cluster_id,
        required=True,
        help="Identificador unico del cluster (formato: cluster-<region>-<numero>).",
    )

    parser.add_argument(
        "-t", "--timeout",
        type=parse_timeout,
        default=2.5,
        help="Tiempo de espera limite para las peticiones HTTP (0.1s - 5.0s).",
    )

    parser.add_argument(
        "--chaos",
        action="store_true",
        help="Forzar inyeccion de caos real en las APIs de nube.",
    )

    parser.add_argument(
        "-m", "--mode",
        choices=["nominal", "debug", "emergency"],
        default="nominal",
        help="Modo de operacion del despachador de telemetria.",
    )

    return parser


async def async_main():
    parser = build_cli_parser()
    args = parser.parse_args()

    logger.info("=" * 64)
    logger.info("INICIANDO MONITOREO MULTICLOUD: PROYECTO TRITON")
    logger.info("=" * 64)
    logger.info(f"Cluster objetivo: {args.cluster_id}")
    logger.info(f"Modo operativo: {args.mode.upper()}")
    logger.info(f"Proveedores seleccionados: {', '.join(args.proveedores)}")
    logger.info(f"Timeout limite configurado: {args.timeout}s")
    if args.chaos:
        logger.warning("MODO CAOS ACTIVADO: se inyectaran fallos reales de red.")
    logger.info("=" * 64)

    try:
        results = await scan_all_providers(args.proveedores, args.timeout, use_chaos=args.chaos)

        logger.info("ESCANEO COMPLETADO SIN ANOMALIAS:")
        for r in results:
            logger.info(
                f"{r['provider']} -> Latencia: {r['latency_sec']:.3f}s | "
                f"ID de Evento: {r['payload_id']} | Estado: {r['status']}"
            )

    except* ProviderTimeoutError as group:
        logger.error(f"ANOMALIA: TIMEOUTS EN PROVEEDORES CLOUD ({len(group.exceptions)} incidentes):")
        for exc in group.exceptions:
            logger.error(f"Fallo: {exc}")
            for note in getattr(exc, "__notes__", []):
                logger.error(f"[FORENSE TRITON] {note}")
        # Volcado forense completo del grupo al log JSON (arbol recursivo con causas y notas)
        logger.debug("Volcado del ExceptionGroup de timeouts", exc_info=group)

    except* CorruptedPayloadError as group:
        logger.error(f"ANOMALIA: PAYLOADS CORRUPTOS O ESTATUS HTTP FALLIDOS ({len(group.exceptions)} incidentes):")
        for exc in group.exceptions:
            logger.error(f"Fallo: {exc}")
            for note in getattr(exc, "__notes__", []):
                logger.error(f"[FORENSE TRITON] {note}")
        logger.debug("Volcado del ExceptionGroup de payloads corruptos", exc_info=group)

    except* NetworkPeeringError as group:
        logger.error(f"ANOMALIA: FALLOS DE CONECTIVIDAD O DNS ({len(group.exceptions)} incidentes):")
        for exc in group.exceptions:
            logger.error(f"Fallo: {exc}")
            for note in getattr(exc, "__notes__", []):
                logger.error(f"[FORENSE TRITON] {note}")
        logger.debug("Volcado del ExceptionGroup de conectividad", exc_info=group)

    except* TritonError as group:
        logger.error("ERROR OPERACIONAL IMPREVISTO EN EL ECOSISTEMA TRITON:")
        for exc in group.exceptions:
            logger.error(f"Fallo: {exc}")
        logger.debug("Volcado del ExceptionGroup de errores imprevistos", exc_info=group)

    finally:
        # PEP 765: finally solo libera recursos; nunca usar return/break/continue aqui
        logger.info("=" * 64)
        logger.info("FIN DE CICLO: liberando recursos de la operacion Triton.")
        logger.info("=" * 64)

        if hasattr(logger, "listener") and logger.listener:
            logger.listener.stop()


if __name__ == "__main__":
    asyncio.run(async_main())
