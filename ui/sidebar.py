"""Barra lateral: filtros del análisis y controles de curaduría.

Solo dibuja controles y devuelve la selección. La lógica de recorte vive en
``src.filters``, de modo que el mismo filtro que ve el usuario pueda
reproducirse en un test o alimentar el prompt del módulo de IA.
"""

from __future__ import annotations

import streamlit as st

from src import config
from src.filters import Filtros, opciones_disponibles


def construir(ssot) -> tuple[Filtros, str]:
    """Dibuja la barra lateral completa.

    Args:
        ssot: Sola Fuente de Verdad, para poblar las opciones disponibles.

    Returns:
        Tupla (filtros seleccionados, política de duplicados elegida).
    """
    opciones = opciones_disponibles(ssot)

    with st.sidebar:
        st.title("TechLogistics S.A.S.")
        st.caption("Sistema de Soporte a la Decisión")

        st.markdown("### Filtros del análisis")

        rango = st.date_input(
            "Rango de fechas de venta",
            value=(opciones["fecha_min"], opciones["fecha_max"]),
            min_value=opciones["fecha_min"], max_value=opciones["fecha_max"],
            help="Acota el periodo. Todas las pestañas se recalculan.")
        # date_input devuelve una tupla incompleta mientras el usuario elige
        # la segunda fecha; hay que tolerarlo o la app revienta a mitad de clic.
        desde, hasta = (rango if isinstance(rango, tuple) and len(rango) == 2
                        else (opciones["fecha_min"], opciones["fecha_max"]))

        categorias = st.multiselect(
            "Categoría", options=opciones["categorias"],
            help="Vacío = todas. 'Sin_Catalogo_Oficial' son las ventas cuyo "
                 "SKU no existe en el maestro de inventario.")

        bodegas = st.multiselect(
            "Bodega de origen", options=opciones["bodegas"],
            help="Vacío = todas.")

        canales = st.multiselect(
            "Canal de venta", options=opciones["canales"],
            help="Vacío = todos. Permite aislar el canal Online que la junta "
                 "señala en la pregunta de rentabilidad.")

        incluir_fantasma = st.toggle(
            "Incluir venta sin catálogo", value=True,
            help="Las ventas cuyo SKU no está en el maestro no tienen costo "
                 "conocido, así que no aportan margen. Se incluyen por "
                 "defecto para que el ingreso total siga siendo trazable.")

        st.divider()

        if st.button("Refrescar análisis", use_container_width=True,
                     type="primary"):
            st.cache_data.clear()
            st.rerun()

        with st.expander("Opciones de curaduría"):
            politica = st.radio(
                "Colisión de `Feedback_ID`",
                options=["conservar", "eliminar"],
                format_func=lambda v: {
                    "conservar": "Conservar y reparar la llave",
                    "eliminar": "Eliminar repeticiones",
                }[v],
                help=(
                    "El activo de feedback no contiene duplicados reales: los "
                    "identificadores repetidos apuntan a transacciones "
                    "distintas, con clientes y calificaciones distintos. "
                    "Conservar repara la llave sin perder opiniones; eliminar "
                    "aplica la lectura literal del enunciado y descarta 500 "
                    "registros legítimos."))

        st.divider()
        st.caption(
            f"Validación temporal contra la fecha del sistema: "
            f"**{config.fecha_corte()}**")

    filtros = Filtros(
        fecha_desde=desde, fecha_hasta=hasta,
        categorias=tuple(categorias), bodegas=tuple(bodegas),
        canales=tuple(canales), incluir_fantasma=incluir_fantasma)

    return filtros, politica
