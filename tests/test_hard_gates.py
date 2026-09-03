"""Verificacion automatica de los hard gates de la consigna sobre el codigo fuente."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def _all_nodes(tree):
    yield from ast.walk(tree)


def test_finally_sin_control_de_flujo():
    """PEP 765: prohibido return/break/continue dentro de bloques finally."""
    for py_file in SRC.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in _all_nodes(tree):
            if isinstance(node, (ast.Try, ast.TryStar)) and node.finalbody:
                for stmt in node.finalbody:
                    for sub in ast.walk(stmt):
                        assert not isinstance(sub, (ast.Return, ast.Break, ast.Continue)), (
                            f"{py_file.name}: sentencia de control de flujo dentro de finally"
                        )


def test_sin_except_baseexception_ni_except_pass():
    """Prohibido capturar BaseException o silenciar con except: pass."""
    for py_file in SRC.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in _all_nodes(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    raise AssertionError(f"{py_file.name}: except: desnudo encontrado")
                if isinstance(node.type, ast.Name) and node.type.id == "BaseException":
                    raise AssertionError(f"{py_file.name}: captura de BaseException")
