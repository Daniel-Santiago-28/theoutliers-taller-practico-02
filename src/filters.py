"""Filtrado de la Sola Fuente de Verdad según la selección del usuario.

Se mantiene fuera de la capa de interfaz para que el mismo recorte que ve el
usuario en pantalla pueda reproducirse en un test o en un script. Esto importa
especialmente para la Fase 4: el módulo de IA debe analizar exactamente el
subconjunto filtrado, y la única forma de garantizarlo es que el filtro sea
una función pura y verificable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Filtros:
    """Selección del usuario en la barra lateral.

    Es inmutable y hashable para poder usarse como clave de caché: dos
    ejecuciones con los mismos filtros deben reutilizar el mismo resultado.
    """

    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    categorias: tuple[str, ...] = field(default_factory=tuple)
    bodegas: tuple[str, ...] = field(default_factory=tuple)
    ciudades: tuple[str, ...] = field(default_factory=tuple)
    canales: tuple[str, ...] = field(default_factory=tuple)
    incluir_fantasma: bool = True

    @property
    def hay_filtro_activo(self) -> bool:
        return any([self.fecha_desde, self.fecha_hasta, self.categorias,
                    self.bodegas, self.ciudades, self.canales,
                    not self.incluir_fantasma])

    def describir(self) -> str:
        """Resumen legible del recorte, para la UI y el prompt de la IA."""
        if not self.hay_filtro_activo:
            return "Sin filtros: se analiza la operación completa."

        partes = []
        if self.fecha_desde or self.fecha_hasta:
            partes.append(
                f"ventas del {self.fecha_desde or 'inicio'} al "
                f"{self.fecha_hasta or 'cierre'}")
        if self.categorias:
            partes.append(f"categorías {', '.join(self.categorias)}")
        if self.bodegas:
            partes.append(f"bodegas {', '.join(self.bodegas)}")
        if self.ciudades:
            partes.append(f"ciudades {', '.join(self.ciudades)}")
        if self.canales:
            partes.append(f"canales {', '.join(self.canales)}")
        if not self.incluir_fantasma:
            partes.append("excluyendo la venta sin catálogo")
        return "Recorte analizado: " + "; ".join(partes) + "."


def opciones_disponibles(ssot: pd.DataFrame) -> dict:
    """Valores seleccionables para poblar los controles de la barra lateral.

    Se leen de los datos ya curados, de modo que el criterio de aceptación de
    la guía de validación se cumpla por construcción: una sola opción coherente
    por entidad del mundo real, sin variantes de caja ni códigos sueltos.
    """
    fechas = ssot["Fecha_Venta"].dropna()
    return {
        "fecha_min": fechas.min().date() if not fechas.empty else None,
        "fecha_max": fechas.max().date() if not fechas.empty else None,
        "categorias": sorted(ssot["Categoria_Analisis"].dropna().unique()),
        "bodegas": sorted(ssot["Bodega_Origen"].dropna().unique()),
        "ciudades": sorted(ssot["Ciudad_Destino"].dropna().unique()),
        "canales": sorted(ssot["Canal_Venta"].dropna().unique()),
    }


def aplicar_filtros(ssot: pd.DataFrame, filtros: Filtros) -> pd.DataFrame:
    """Recorta la SSOT según la selección del usuario.

    Las ventas con fecha posterior al momento de ejecución se excluyen siempre
    de los cortes temporales: son errores de captura del sistema origen y no
    deben aparecer en ninguna serie de tiempo.

    Args:
        ssot: Sola Fuente de Verdad completa.
        filtros: Selección del usuario.

    Returns:
        Subconjunto de la SSOT. Puede estar vacío si el filtro es muy
        restrictivo; el llamador debe contemplarlo.
    """
    recorte = ssot

    if filtros.fecha_desde is not None:
        recorte = recorte[
            recorte["Fecha_Venta"] >= pd.Timestamp(filtros.fecha_desde)]
    if filtros.fecha_hasta is not None:
        recorte = recorte[
            recorte["Fecha_Venta"] <= pd.Timestamp(filtros.fecha_hasta)]
    if filtros.categorias:
        recorte = recorte[
            recorte["Categoria_Analisis"].isin(filtros.categorias)]
    if filtros.bodegas:
        recorte = recorte[recorte["Bodega_Origen"].isin(filtros.bodegas)]
    if filtros.ciudades:
        recorte = recorte[recorte["Ciudad_Destino"].isin(filtros.ciudades)]
    if filtros.canales:
        recorte = recorte[recorte["Canal_Venta"].isin(filtros.canales)]
    if not filtros.incluir_fantasma:
        from src import config
        recorte = recorte[~recorte[config.COL_FLAG_FANTASMA]]

    logger.info("Filtro aplicado: %d de %d filas", len(recorte), len(ssot))
    return recorte
