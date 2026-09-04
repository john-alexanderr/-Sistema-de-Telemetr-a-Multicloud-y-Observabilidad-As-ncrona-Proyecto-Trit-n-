import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "src" / "app_operator.py"


def test_argumentos_invalidos_abortan_con_codigo_2():
    result = subprocess.run(
        [sys.executable, str(APP), "AWS", "GCP", "-c", "cluster-invalido-id", "-t", "9.5"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert "cluster" in result.stderr.lower() or "timeout" in result.stderr.lower()


def test_timeout_fuera_de_rango_aborta_con_codigo_2():
    result = subprocess.run(
        [sys.executable, str(APP), "AWS", "-c", "cluster-us-east-01", "-t", "0.05"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2


def test_salida_quiet_y_verbose_es_mutuamente_excluyente():
    result = subprocess.run(
        [
            sys.executable,
            str(APP),
            "AWS",
            "-c",
            "cluster-us-east-01",
            "-q",
            "-v",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert "not allowed with argument" in result.stderr
