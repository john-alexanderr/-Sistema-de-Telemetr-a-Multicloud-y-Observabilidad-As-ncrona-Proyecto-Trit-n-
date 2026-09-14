import argparse
import re


def parse_timeout(value: str) -> float:
    """Valida el timeout de la CLI en la frontera del programa.

    Acepta un flotante entre 0.1 y 5.0 segundos. Fuera de rango o texto no
    numerico se rechaza con argparse.ArgumentTypeError, que es el tipo que
    argparse entiende para imprimir la ayuda y salir con codigo 2 sin abrir
    el event loop ni tocar la red.
    """
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
    """Valida el identificador de cluster con la regex de la solucion patron.

    Formato: cluster-<region>-<numero de dos digitos>, por ejemplo
    cluster-us-east-01. Solo minusculas, dos segmentos de region como
    minimo y el numero final siempre de dos digitos.
    """
    pattern = r"^cluster-[a-z]{2,10}-[a-z]+-\d{2}$"
    if not re.fullmatch(pattern, value):
        raise argparse.ArgumentTypeError(
            f"El ID del cluster '{value}' no cumple con el formato requerido "
            f"(ejemplo valido: 'cluster-us-east-01')."
        )
    return value
