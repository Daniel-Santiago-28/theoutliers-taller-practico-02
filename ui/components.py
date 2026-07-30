"""Componentes de interfaz reutilizables entre pestañas.

El principal es el panel de veredicto estadístico, que se usa en las cinco
preguntas gerenciales. Tenerlo centralizado hace que el criterio para declarar
un hallazgo sólido sea idéntico en todas, y que el evaluador vea una postura
metodológica consistente en lugar de cinco improvisaciones.
"""

from __future__ import annotations

import streamlit as st

from src.analytics import Veredicto
from ui import theme

# El color de estado nunca viaja solo: siempre acompañado de ícono y etiqueta.
_ESTILO_VEREDICTO = {
    "Hallazgo sólido": (theme.ESTADO_BUENO, "✓"),
    "Significativo pero irrelevante": (theme.ESTADO_ALERTA, "▲"),
    "Sin evidencia": (theme.ESTADO_GRAVE, "○"),
}


def mostrar_veredicto(veredicto: Veredicto, titulo: str) -> None:
    """Panel con la prueba estadística, su tamaño de efecto y su lectura.

    Muestra siempre las dos condiciones por separado —significancia y
    magnitud— porque son distintas y confundirlas es el error que este
    proyecto busca evitar: con más de 8.000 observaciones, casi cualquier
    diferencia cruza el umbral de significancia sin ser relevante.

    Args:
        veredicto: Resultado de una prueba de ``src.analytics``.
        titulo: Pregunta concreta que la prueba responde.
    """
    color, icono = _ESTILO_VEREDICTO.get(
        veredicto.etiqueta, (theme.TINTA_MUTED, "•"))

    with st.container(border=True):
        st.markdown(
            f"**{titulo}**  \n"
            f"<span style='color:{color};font-weight:600'>{icono} "
            f"{veredicto.etiqueta}</span>", unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        col1.metric(veredicto.nombre_efecto or "Estadístico",
                    veredicto.efecto_texto(decimales=3),
                    help="Tamaño de efecto: cuánto importa la diferencia")
        col2.metric("Valor p", f"{veredicto.p_valor:.4f}",
                    help="Probabilidad de ver esto si no hubiera efecto real")
        col3.metric("Magnitud", veredicto.magnitud.capitalize(),
                    help=f"n = {veredicto.n:,} observaciones")

        st.caption(veredicto.lectura)

        if veredicto.significativo and not veredicto.concluyente:
            st.caption(
                f"⚠️ El valor p cruza el umbral de {0.05}, pero el tamaño de "
                f"efecto es {veredicto.magnitud}. Con n = {veredicto.n:,} eso "
                f"era esperable: la muestra es tan grande que detecta "
                f"diferencias sin importancia práctica. **No sostiene una "
                f"recomendación.**")


def fila_kpis(items: list[tuple[str, str, str]]) -> None:
    """Fila de indicadores.

    Args:
        items: Lista de tuplas (etiqueta, valor, ayuda).
    """
    columnas = st.columns(len(items))
    for columna, (etiqueta, valor, ayuda) in zip(columnas, items):
        columna.metric(etiqueta, valor, help=ayuda)


def aviso_sin_datos(contexto: str = "") -> None:
    """Mensaje estándar cuando el filtro deja el recorte vacío."""
    st.warning(
        f"El filtro aplicado no deja transacciones analizables. {contexto} "
        "Amplíe el rango de fechas o quite alguna restricción del panel "
        "lateral.", icon="⚠️")
