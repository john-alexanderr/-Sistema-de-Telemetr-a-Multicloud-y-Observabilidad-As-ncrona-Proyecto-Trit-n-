"""Validadores declarativos para la frontera CLI.

Alternativa profesional no implementada: pydantic para validacion declarativa de modelos.
"""

import argparse
import re


def parse_timeout(value: str) -> float:
    """Sanitiza el timeout: debe ser un flotante en el rango [0.1, 5.0] segundos."""
    try:
        timeout = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Timeout invalido '{value}': no es un numero.")

    if not (0.1 <= timeout <= 5.0):
        raise argparse.ArgumentTypeError(
            f"Timeout invalido '{value}': debe estar entre 0.1 y 5.0 segundos."
        )
    return timeout


def parse_cluster_id(value: str) -> str:
    """Valida el ID del cluster contra el patron cluster-<region>-<numero> (ej: cluster-us-east-01)."""
    pattern = r"^cluster-[a-z]+(?:-[a-z]+)*-\d+$"
    if not re.fullmatch(pattern, value):
        raise argparse.ArgumentTypeError(
            f"El ID del cluster '{value}' no cumple con el formato requerido "
            f"(ejemplo valido: 'cluster-us-east-01')."
        )
    return value
