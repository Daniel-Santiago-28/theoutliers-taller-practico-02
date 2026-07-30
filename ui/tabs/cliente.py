"""Pestaña de Cliente: fidelidad y riesgo operativo.

Cubre las preguntas 4 y 5 del reto analítico. Ambas preguntan por una
relación que el dato no sostiene, así que se presentan en dos niveles: el
análisis solicitado con su veredicto explícito, y debajo lo que sí resulta
medible y accionable.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import analytics
from ui import components, theme


def _seccion_pregunta_4(recorte: pd.DataFrame) -> None:
    """Pregunta 4: diagnóstico de fidelidad."""
    st.subheader("4 · Diagnóstico de fidelidad")
    st.markdown(
        "> *¿Existen categorías de productos con alta disponibilidad (stock "
        "alto) pero con un sentimiento de cliente negativo? Explique la "
        "paradoja: ¿es mala calidad de producto o sobrecosto?*")

    resultado = analytics.analizar_paradoja_fidelidad(recorte)

    if resultado.por_categoria.empty:
        components.aviso_sin_datos(resultado.diagnostico)
        return

    kpis = resultado.kpis
    components.fila_kpis([
        ("Categorías evaluadas", f"{kpis.get('categorias_evaluadas', 0)}",
         "Incluye la venta sin catálogo y los productos sin clasificar"),
        ("Stock medio global",
         f"{kpis.get('stock_medio_global', 0):,.0f} u.",
         "Unidades promedio en bodega"),
        ("Rating medio global",
         f"{kpis.get('rating_medio_global', 0):.2f} / 5",
         "Calificación media de producto"),
        ("Causa dominante del reclamo",
         f"{kpis.get('causa_dominante', '—')} "
         f"{kpis.get('pct_causa_dominante', 0):.0f}%",
         "Sobre los comentarios con causa identificada"),
    ])

    st.divider()

    # --- Nivel 1: ¿existe la paradoja? -----------------------------------
    st.markdown("#### Nivel 1 · ¿Existe la paradoja?")
    st.caption(
        "Para que haya categorías con stock alto y clientes molestos, tanto "
        "el stock como el sentimiento tienen que variar entre categorías. Se "
        "prueban ambas condiciones por separado antes de buscar el cruce.")

    izquierda, derecha = st.columns([3, 2])
    with izquierda:
        st.plotly_chart(theme.grafico_paradoja(resultado.por_categoria),
                        use_container_width=True, key="g_p4_paradoja")
    with derecha:
        components.mostrar_veredicto(
            resultado.veredicto_sentimiento,
            "¿La satisfacción difiere entre categorías?")
        components.mostrar_veredicto(
            resultado.veredicto_stock,
            "¿La disponibilidad difiere entre categorías?")

    st.divider()

    # --- Nivel 2: la disyuntiva calidad vs precio ------------------------
    st.markdown("#### Nivel 2 · ¿Mala calidad o sobrecosto?")
    st.caption(
        "`Comentario_Texto` es un conjunto cerrado de frases, no texto libre. "
        "Se deriva de él la causa raíz del reclamo, que es exactamente la "
        "disyuntiva que plantea la pregunta.")

    izquierda, derecha = st.columns([3, 2])
    with izquierda:
        st.plotly_chart(theme.grafico_causa_raiz(resultado.causa_raiz),
                        use_container_width=True, key="g_p4_causa")
    with derecha:
        components.mostrar_veredicto(
            resultado.veredicto_causa,
            "¿El motivo del reclamo depende de la categoría?")
        reparto = kpis.get("reparto_causas", {})
        if reparto:
            st.markdown("**Reparto global de la causa del reclamo**")
            st.dataframe(
                pd.DataFrame(
                    [{"Causa": k, "% de las quejas": v}
                     for k, v in reparto.items()]),
                use_container_width=True, hide_index=True)

    st.markdown("#### Conclusión para la junta")
    st.info(resultado.diagnostico, icon="💡")

    with st.expander("Ver el detalle por categoría"):
        st.dataframe(resultado.por_categoria, use_container_width=True,
                     hide_index=True)


def _seccion_pregunta_5(recorte: pd.DataFrame) -> None:
    """Pregunta 5: storytelling de riesgo operativo."""
    st.subheader("5 · Storytelling de riesgo operativo")
    st.markdown(
        "> *Visualice la relación entre la antigüedad de la Última Revisión "
        "del stock y la tasa de Tickets de Soporte. ¿Qué bodegas están "
        "operando a ciegas y cómo impacta esto en la satisfacción final?*")

    resultado = analytics.analizar_riesgo_operativo(recorte)

    if resultado.por_bodega.empty:
        components.aviso_sin_datos(resultado.diagnostico)
        return

    kpis = resultado.kpis
    components.fila_kpis([
        ("Sin conteo físico", f"{kpis['antiguedad_meses']:.1f} meses",
         f"Mediana de {kpis['antiguedad_mediana_global']:.0f} días desde la "
         f"última verificación"),
        ("Antigüedad máxima", f"{kpis['antiguedad_maxima']:.0f} días",
         "El SKU peor auditado de la red"),
        ("Bodegas evaluadas", f"{kpis['bodegas_evaluadas']}",
         f"{kpis['bodegas_no_estandar']} sin nomenclatura regional"),
        ("Tasa global de tickets", f"{kpis['tasa_tickets_global']:.1f}%",
         "Ventas con reclamo formal abierto"),
    ])

    st.divider()

    st.markdown("#### Nivel 1 · La relación que plantea la pregunta")
    st.caption(
        "La cadena causal que asume el enunciado tiene tres eslabones: que la "
        "antigüedad difiera entre bodegas, que la tasa de reclamos también "
        "difiera, y que ambas se relacionen. Se prueban los tres.")

    izquierda, derecha = st.columns([3, 2])
    with izquierda:
        st.plotly_chart(
            theme.grafico_antiguedad_vs_tickets(resultado.por_bodega),
            use_container_width=True, key="g_p5_dispersion")
    with derecha:
        components.mostrar_veredicto(
            resultado.veredicto_antiguedad_tickets,
            "¿Más antigüedad implica más reclamos?")
        components.mostrar_veredicto(
            resultado.veredicto_tickets_bodega,
            "¿La tasa de reclamos difiere entre bodegas?")

    st.divider()

    st.markdown("#### Nivel 2 · Qué bodegas operan a ciegas")
    izquierda, derecha = st.columns([3, 2])
    with izquierda:
        st.plotly_chart(
            theme.grafico_antiguedad_bodega(resultado.por_bodega),
            use_container_width=True, key="g_p5_antiguedad")
    with derecha:
        components.mostrar_veredicto(
            resultado.veredicto_antiguedad_bodega,
            "¿La desatención del inventario difiere entre bodegas?")
        st.warning(
            "**La ausencia de reclamos no es evidencia de control.** Un "
            "inventario que lleva más de un año sin verificarse produce "
            "decisiones de reposición sobre stock teórico. El descuadre "
            "existe desde el momento en que se deja de contar; lo que aún no "
            "ocurre es que aflore.", icon="⚠️")

    st.markdown("#### Conclusión para la junta")
    st.info(resultado.diagnostico, icon="💡")

    with st.expander("Ver el detalle por bodega"):
        st.dataframe(resultado.por_bodega, use_container_width=True,
                     hide_index=True)
        st.download_button(
            "Descargar el detalle por bodega",
            data=resultado.por_bodega.to_csv(index=False).encode("utf-8-sig"),
            file_name="pregunta5_riesgo_por_bodega.csv", mime="text/csv",
            key="descarga_p5")


def renderizar(recorte: pd.DataFrame, descripcion_filtro: str) -> None:
    """Dibuja la pestaña de Cliente.

    Args:
        recorte: SSOT ya filtrada por la selección del usuario.
        descripcion_filtro: Texto legible del recorte aplicado.
    """
    st.header("Cliente")
    st.caption(descripcion_filtro)

    if recorte.empty:
        components.aviso_sin_datos()
        return

    _seccion_pregunta_4(recorte)
    st.divider()
    _seccion_pregunta_5(recorte)
