"""Ingesta y validación de esquema de los activos de información.

Principio de diseño: la ingesta es *forense*. Los tres CSV se leen sin ninguna
coerción de tipos ni interpretación de nulos (``dtype=str``,
``keep_default_na=False``), de modo que el DataFrame resultante refleje
exactamente lo que hay en disco.

El motivo es de auditoría: si se dejara a pandas convertir "???" o "nan" a
NaN durante la lectura, el reporte de calidad "antes" mostraría una nulidad
distinta de la real y se perdería la evidencia de qué centinelas usaba cada
sistema fuente. Toda conversión de tipo ocurre después, en ``cleaning``, y
queda registrada.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src import config

logger = logging.getLogger(__name__)


class ErrorIngesta(Exception):
    """Error base de la capa de ingesta."""


class ArchivoFuenteNoEncontrado(ErrorIngesta):
    """El CSV esperado no existe en data/raw/."""


class EsquemaInvalido(ErrorIngesta):
    """El CSV existe pero no cumple el contrato de columnas esperado."""


_RUTAS = {
    "inventario": config.ARCHIVO_INVENTARIO,
    "transacciones": config.ARCHIVO_TRANSACCIONES,
    "feedback": config.ARCHIVO_FEEDBACK,
}


def _leer_csv_crudo(ruta: Path) -> pd.DataFrame:
    """Lee un CSV como texto plano, sin interpretar nulos ni tipos.

    Args:
        ruta: Ruta absoluta al archivo CSV.

    Returns:
        DataFrame donde todas las columnas son de tipo ``object`` (str).

    Raises:
        ArchivoFuenteNoEncontrado: Si la ruta no existe.
        ErrorIngesta: Si el archivo está vacío, corrupto o no es decodificable.
    """
    if not ruta.exists():
        raise ArchivoFuenteNoEncontrado(
            f"No se encontró el archivo fuente: {ruta}. "
            "Verifique que los CSV originales estén en data/raw/."
        )

    # Los datos traen tildes (Medellín, Bogotá, Sí). Se intenta UTF-8 y se
    # cae a latin-1, que es la codificación típica de exportes de ERP en es-CO.
    for codificacion in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(
                ruta,
                dtype=str,
                keep_default_na=False,
                na_values=[],
                encoding=codificacion,
            )
        except UnicodeDecodeError:
            logger.warning("Fallo decodificando %s como %s", ruta.name, codificacion)
            continue
        except pd.errors.EmptyDataError as exc:
            raise ErrorIngesta(f"El archivo {ruta.name} está vacío.") from exc
        except pd.errors.ParserError as exc:
            raise ErrorIngesta(
                f"El archivo {ruta.name} no pudo parsearse como CSV: {exc}"
            ) from exc

    raise ErrorIngesta(
        f"No fue posible decodificar {ruta.name} con UTF-8 ni latin-1."
    )


def validar_esquema(df: pd.DataFrame, nombre: str) -> None:
    """Verifica que el DataFrame cumpla el contrato de columnas declarado.

    Falla de forma ruidosa y temprana: un cambio silencioso de esquema en el
    archivo fuente invalidaría todo el análisis aguas abajo.

    Args:
        df: DataFrame recién ingerido.
        nombre: Clave del dataset ('inventario', 'transacciones', 'feedback').

    Raises:
        EsquemaInvalido: Si faltan columnas esperadas.
    """
    esperadas = config.ESQUEMAS[nombre]
    faltantes = [col for col in esperadas if col not in df.columns]
    if faltantes:
        raise EsquemaInvalido(
            f"Al dataset '{nombre}' le faltan columnas obligatorias: {faltantes}. "
            f"Columnas encontradas: {list(df.columns)}"
        )

    inesperadas = [col for col in df.columns if col not in esperadas]
    if inesperadas:
        # No es fatal, pero debe quedar registrado: puede ser información
        # valiosa no documentada en el diccionario de datos.
        logger.warning(
            "El dataset '%s' trae columnas no declaradas en el esquema: %s",
            nombre,
            inesperadas,
        )


def cargar_crudo(nombre: str) -> pd.DataFrame:
    """Carga un dataset crudo y valida su esquema.

    Args:
        nombre: 'inventario', 'transacciones' o 'feedback'.

    Returns:
        DataFrame en crudo, todas las columnas como texto.

    Raises:
        ValueError: Si el nombre de dataset no es reconocido.
        ErrorIngesta: Ante cualquier fallo de lectura o de esquema.
    """
    if nombre not in _RUTAS:
        raise ValueError(
            f"Dataset desconocido: '{nombre}'. Opciones: {list(_RUTAS)}"
        )

    df = _leer_csv_crudo(_RUTAS[nombre])
    validar_esquema(df, nombre)
    logger.info("Ingerido '%s': %d filas x %d columnas", nombre, *df.shape)
    return df


def cargar_todos_crudos() -> dict[str, pd.DataFrame]:
    """Carga los tres activos de información en crudo.

    Returns:
        Diccionario {nombre_dataset: DataFrame crudo}.
    """
    return {nombre: cargar_crudo(nombre) for nombre in _RUTAS}
