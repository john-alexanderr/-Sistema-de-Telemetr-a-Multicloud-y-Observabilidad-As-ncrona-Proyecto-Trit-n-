import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "src" / "app_operator.py"
HOST_INEXISTENTE = "https://host-inexistente-triton.invalid"


def ejecutar(nombre: str, comando: list, entorno: dict | None = None) -> bool:
    print(f"\n=== ESCENARIO DE CAOS: {nombre} ===")
    print(f"$ python src/app_operator.py {' '.join(comando[2:])}")
    resultado = subprocess.run(
        comando, cwd=RAIZ, env=entorno or os.environ.copy(), timeout=120, check=False
    )
    estado = "OK: la aplicacion siguio de pie" if resultado.returncode == 0 else f"FALLO: exit code {resultado.returncode}"
    print(f"-> {estado}")
    return resultado.returncode == 0


def main() -> int:
    escenarios = [
        (
            "Timeout forzado por latencia extrema (httpbin delay/3)",
            [sys.executable, str(APP), "AWS", "-c", "cluster-us-east-01", "-t", "0.5", "--chaos"],
            None,
        ),
        (
            "Estatus HTTP fallido inyectado (httpbin status/504)",
            [sys.executable, str(APP), "Azure", "-c", "cluster-us-east-01", "-t", "4.0", "--chaos"],
            None,
        ),
        (
            "Payload corrupto inyectado (httpbin devuelve XML)",
            [sys.executable, str(APP), "GCP", "-c", "cluster-us-east-01", "-t", "4.0", "--chaos"],
            None,
        ),
        (
            "Tormenta total: los tres proveedores colapsan a la vez",
            [sys.executable, str(APP), "AWS", "Azure", "GCP", "-c", "cluster-us-west-02", "-t", "1.5", "--chaos"],
            None,
        ),
        (
            "Perdida de peering: URLs redirigidas a un host inexistente (DNS)",
            [sys.executable, str(APP), "AWS", "Azure", "GCP", "-c", "cluster-us-east-01", "-t", "3.0"],
            {**os.environ, "TRITON_BASE_URL": HOST_INEXISTENTE},
        ),
    ]

    resultados = [ejecutar(nombre, comando, entorno) for nombre, comando, entorno in escenarios]

    print("\n=== VALIDACION FORENSE DEL REGISTRO ACUMULADO ===")
    forense = subprocess.run([sys.executable, str(RAIZ / "scripts" / "forensic_validator.py")], cwd=RAIZ, check=False)

    exitosos = sum(resultados)
    print(f"\nResumen: {exitosos}/{len(resultados)} escenarios mantuvieron la aplicacion de pie.")
    if exitosos == len(resultados) and forense.returncode == 0:
        print("SUITE DE CAOS SUPERADA")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
