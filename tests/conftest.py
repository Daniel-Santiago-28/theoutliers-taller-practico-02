"""Configuración compartida de pytest: expone la raíz del proyecto al path."""

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src import ingest  # noqa: E402


@pytest.fixture(scope="session")
def datos_crudos():
    """Carga única de los tres activos crudos para toda la sesión de tests."""
    return ingest.cargar_todos_crudos()
