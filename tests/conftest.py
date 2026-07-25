"""Configuración compartida de pytest: expone la raíz del proyecto al path."""

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src import cleaning, ingest, integration  # noqa: E402


@pytest.fixture(scope="session")
def datos_crudos():
    """Carga única de los tres activos crudos para toda la sesión de tests."""
    return ingest.cargar_todos_crudos()


@pytest.fixture(scope="session")
def pipeline_limpieza(datos_crudos):
    """Pipeline de curaduría, ejecutado una sola vez por sesión.

    Alcance de sesión y no de módulo: la limpieza recorre 17.000 filas y varios
    módulos de prueba la necesitan, así que repetirla multiplicaría el tiempo
    de la suite sin aportar aislamiento real (el pipeline es puro).
    """
    return cleaning.ejecutar_pipeline(datos_crudos)


@pytest.fixture(scope="session")
def integrado(pipeline_limpieza):
    """Sola Fuente de Verdad, construida una sola vez por sesión."""
    return integration.construir_ssot(pipeline_limpieza.limpios,
                                      pipeline_limpieza.crudos)
