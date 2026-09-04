"""Validador forense de telemetria.

Abre el log plano y los backups comprimidos .gz, comprueba que cada linea sea JSON valido,
verifica los metadatos obligatorios y la presencia del arbol completo de excepciones.
"""

import gzip
import json
import re
import sys
from datetime import datetime
from pathlib import Path

CAMPOS_OBLIGATORIOS = ("timestamp", "level", "message", "process", "thread_name", "async_task")
HTTP_STATUS_PATTERN = re.compile(r"\b[45]\d{2}\b")


def abrir_log(ruta: Path):
    if ruta.suffix == ".gz":
        return gzip.open(ruta, "rt", encoding="utf-8")
    return open(ruta, "r", encoding="utf-8")


def validar_evento(evento: dict, errores: list) -> int:
    """Valida un evento JSON. Devuelve 1 si contiene un arbol de excepciones."""
    for campo in CAMPOS_OBLIGATORIOS:
        if campo not in evento:
            errores.append(f"falta el campo obligatorio '{campo}'")

    timestamp = evento.get("timestamp", "")
    if not timestamp.endswith("Z"):
        errores.append(f"timestamp sin sufijo UTC estricto: {timestamp}")
    else:
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            errores.append(f"timestamp no es ISO 8601 valido: {timestamp}")

    return validar_arbol(evento.get("exception_tree"), errores)


def validar_arbol(nodo, errores: list, ancestros: tuple[dict, ...] = ()) -> int:
    """Recorre recursivamente el arbol de excepciones serializado."""
    if nodo is None:
        return 0
    if not isinstance(nodo, dict):
        errores.append("nodo de excepcion no es un objeto JSON")
        return 0
    if not nodo.get("class") or "message" not in nodo:
        errores.append("nodo de excepcion incompleto")

    if nodo.get("class") == "HTTPStatusError":
        message = str(nodo.get("message", ""))
        contexto = " ".join(
            note
            for ancestro in ancestros
            for note in ancestro.get("notes", [])
        )
        if not HTTP_STATUS_PATTERN.search(message):
            errores.append("HTTPStatusError sin codigo de estado HTTP en el mensaje")
        if "HTTP_Status_Code:" not in contexto:
            errores.append("HTTPStatusError sin nota HTTP_Status_Code en su excepcion semantica")
        if "HTTP_Method:" not in contexto:
            errores.append("HTTPStatusError sin nota HTTP_Method en su excepcion semantica")

    total = 1
    siguientes_ancestros = (*ancestros, nodo)
    for anidada in nodo.get("nested_exceptions", []):
        total += validar_arbol(anidada, errores, siguientes_ancestros)
    total += validar_arbol(nodo.get("cause"), errores, siguientes_ancestros)
    return total


def main() -> int:
    ruta_log = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("triton_services.log")
    if not ruta_log.exists():
        print(f"No existe el archivo de log: {ruta_log}")
        return 1

    archivos = [ruta_log]
    for indice in range(1, 4):
        plano = ruta_log.with_name(f"{ruta_log.name}.{indice}")
        comprimido = ruta_log.with_name(f"{ruta_log.name}.{indice}.gz")
        if plano.exists():
            archivos.append(plano)
        if comprimido.exists():
            archivos.append(comprimido)

    total_eventos = 0
    eventos_error = 0
    arboles = 0
    errores = []

    for archivo in archivos:
        with abrir_log(archivo) as manejador:
            for numero, linea in enumerate(manejador, start=1):
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    evento = json.loads(linea)
                except json.JSONDecodeError as err:
                    errores.append(f"{archivo.name}:{numero} JSON invalido ({err})")
                    continue
                total_eventos += 1
                if evento.get("level") in ("ERROR", "CRITICAL"):
                    eventos_error += 1
                arboles += validar_evento(evento, errores)

    if eventos_error and not arboles:
        errores.append("hay eventos de error pero no se encontro ningun arbol de excepciones")

    print("=== VALIDACION FORENSE DE TELEMETRIA TRITON ===")
    print(f"Archivos inspeccionados : {len(archivos)} ({', '.join(a.name for a in archivos)})")
    print(f"Eventos JSON validos    : {total_eventos}")
    print(f"Eventos de error        : {eventos_error}")
    print(f"Arboles de excepciones  : {arboles}")

    if errores:
        print(f"Errores detectados      : {len(errores)}")
        for detalle in errores[:10]:
            print(f"  - {detalle}")
        return 1

    print("Resultado               : TELEMETRIA INTEGRA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
