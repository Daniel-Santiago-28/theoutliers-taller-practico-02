"""Pestaña de Operaciones: rentabilidad, logística y venta invisible.

Cubre las preguntas 1, 2 y 3 del reto analítico. Cada pregunta se presenta con
la misma estructura: indicadores, evidencia visual, veredicto estadístico y
conclusión de negocio.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import analytics
from ui import components, theme


def _seccion_pregunta_1(recorte: pd.DataFrame) -> None:
    """Pregunta 1: fuga de capital y rentabilidad."""
    st.subheader("1 · Fuga de capital y rentabilidad")
    st.markdown(
        "> *Localice los SKU que se están vendiendo con margen negativo. "
        "¿Representan una pérdida aceptable por volumen o es una falla "
        "crítica de precios en el canal Online?*")

    resultado = analytics.analizar_fuga_capital(recorte)

    if not resultado.kpis:
        components.aviso_sin_datos(resultado.diagnostico)
        return

    kpis = resultado.kpis
    components.fila_kpis([
        ("Pérdida acumulada", f"USD {kpis['perdida_total_usd']:,.0f}",
         "Suma del margen neto de los SKU deficitarios"),
        ("SKU deficitarios",
         f"{kpis['skus_con_perdida']:,} ({kpis['pct_skus_con_perdida']:.1f}%)",
         "SKU cuyo margen neto acumulado es negativo"),
        ("Ventas con pérdida", f"{kpis['pct_trx_con_perdida']:.1f}%",
         f"{kpis['trx_con_perdida']:,} transacciones deficitarias"),
        ("Erosión del margen", f"{kpis['erosion_pct']:.1f}%",
         "Cuánto se come la pérdida de la utilidad que sí se genera"),
    ])

    for advertencia in resultado.advertencias:
        st.caption(f"ℹ️ {advertencia}")

    st.divider()

    # --- Las dos hipótesis de la junta, contrastadas ---------------------
    st.markdown("#### Las dos hipótesis de la junta")

    izquierda, derecha = st.columns(2)
    with izquierda:
        st.plotly_chart(theme.grafico_volumen_vs_margen(resultado.por_sku),
                        use_container_width=True, key="g_p1_volumen")
        components.mostrar_veredicto(
            resultado.veredicto_volumen,
            "¿Es una pérdida aceptable por volumen (producto gancho)?")

    with derecha:
        st.plotly_chart(theme.grafico_tasa_por_canal(resultado.por_canal),
                        use_container_width=True, key="g_p1_canal")
        components.mostrar_veredicto(
            resultado.veredicto_canal,
            "¿Es una falla de precios del canal Online?")
        st.dataframe(
            resultado.por_canal[[
                "Canal_Venta", "transacciones", "tasa_negativa_pct",
                "perdida_usd", "margen_neto_usd"]].rename(columns={
                    "Canal_Venta": "Canal", "transacciones": "Trx",
                    "tasa_negativa_pct": "% deficitaria",
                    "perdida_usd": "Pérdida USD",
                    "margen_neto_usd": "Margen neto USD"}),
            use_container_width=True, hide_index=True)

    st.divider()

    # --- La hipótesis que la junta no consideró --------------------------
    st.markdown("#### La causa que la junta no consideró")

    izquierda, derecha = st.columns([3, 2])
    with izquierda:
        st.plotly_chart(theme.grafico_costo_vs_precio(resultado.por_sku),
                        use_container_width=True, key="g_p1_costo_precio")
    with derecha:
        components.mostrar_veredicto(
            resultado.veredicto_pricing,
            "¿El precio de venta responde al costo de compra?")
        st.markdown(
            "Si existiera una política de precios, los puntos formarían una "
            "banda ascendente por encima de la diagonal. Lo que se observa es "
            "una nube sin pendiente: **el precio no lleva información sobre "
            "el costo**. Todo lo que cae bajo la línea punteada se vende por "
            "debajo de lo que costó comprarlo.")

    st.plotly_chart(theme.grafico_pareto_perdida(resultado.pareto),
                    use_container_width=True, key="g_p1_pareto")

    st.divider()

    # --- Conclusión -------------------------------------------------------
    st.markdown("#### Conclusión para la junta")
    st.info(resultado.diagnostico, icon="💡")

    with st.expander("Ver los 50 SKU más deficitarios"):
        peores = resultado.por_sku.head(50)[[
            "SKU_ID", "categoria", "bodega", "unidades", "ingreso_usd",
            "costo_unitario_usd", "precio_medio_usd", "margen_unitario_usd",
            "margen_neto_usd", "margen_pct"]].rename(columns={
                "SKU_ID": "SKU", "categoria": "Categoría", "bodega": "Bodega",
                "unidades": "Unidades", "ingreso_usd": "Ingreso USD",
                "costo_unitario_usd": "Costo unit.",
                "precio_medio_usd": "Precio medio",
                "margen_unitario_usd": "Margen unit.",
                "margen_neto_usd": "Margen neto USD",
                "margen_pct": "Margen %"})
        st.dataframe(peores, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar el detalle por SKU",
            data=resultado.por_sku.to_csv(index=False).encode("utf-8-sig"),
            file_name="pregunta1_margen_por_sku.csv", mime="text/csv",
            key="descarga_p1")


def _seccion_pregunta_2(recorte: pd.DataFrame) -> None:
    """Pregunta 2: crisis logística y cuellos de botella."""
    st.subheader("2 · Crisis logística y cuellos de botella")
    st.markdown(
        "> *¿En qué ciudades y bodegas la correlación entre Tiempo de Entrega "
        "y NPS bajo es más fuerte? Identifique la zona que requiere un cambio "
        "inmediato de operador.*")

    resultado = analytics.analizar_crisis_logistica(recorte)
    kpis = resultado.kpis

    components.fila_kpis([
        ("Envíos en estado adverso",
         f"{kpis['tasa_envio_adverso_pct']:.1f}%",
         f"Retrasados, perdidos o devueltos, sobre "
         f"{kpis['trx_con_estado']:,} envíos con estado registrado"),
        ("Entrega mediana", f"{kpis['entrega_mediana_dias']:.0f} días",
         "Mediana de días entre pedido y entrega"),
        ("Percentil 90", f"{kpis['entrega_p90_dias']:.0f} días",
         "Una de cada diez entregas supera este plazo"),
        ("Correlaciones sólidas",
         f"{kpis['correlaciones_significativas']} de "
         f"{kpis['correlaciones_evaluadas']}",
         "Correlaciones demora–NPS que sobreviven a Bonferroni"),
    ])

    st.divider()

    # --- Nivel 1: el ranking que pide el enunciado -----------------------
    st.markdown("#### Nivel 1 · El ranking solicitado")
    st.caption(
        "Correlación entre tiempo de entrega y NPS dentro de cada plaza y "
        "cada bodega. Se aplica corrección de Bonferroni porque evaluar diez "
        "grupos a un alfa de 0,05 produce un falso positivo el 40 % de las "
        "veces. Las barras que no sobreviven se dibujan atenuadas.")

    izquierda, derecha = st.columns(2)
    with izquierda:
        st.plotly_chart(
            theme.grafico_correlaciones(
                resultado.correlaciones_ciudad, "Ciudad_Destino",
                "Demora vs NPS por ciudad"), use_container_width=True,
            key="g_p2_corr_ciudad")
    with derecha:
        st.plotly_chart(
            theme.grafico_correlaciones(
                resultado.correlaciones_bodega, "Bodega_Origen",
                "Demora vs NPS por bodega"), use_container_width=True,
            key="g_p2_corr_bodega")

    if kpis["correlaciones_significativas"] == 0:
        st.error(
            f"**Hallazgo nulo.** Ninguna de las "
            f"{kpis['correlaciones_evaluadas']} correlaciones evaluadas es "
            f"distinguible de cero tras corregir por comparaciones múltiples. "
            f"Todas las barras están atenuadas porque todas son ruido de "
            f"muestreo. Ordenar estas plazas y señalar la primera sería "
            f"presentar azar como diagnóstico.", icon="🚫")

    with st.expander("Ver el detalle estadístico por grupo"):
        for etiqueta, tabla in (("Ciudades", resultado.correlaciones_ciudad),
                                ("Bodegas", resultado.correlaciones_bodega)):
            st.markdown(f"**{etiqueta}**")
            st.dataframe(tabla, use_container_width=True, hide_index=True)

    st.divider()

    # --- Nivel 2: donde sí hay señal -------------------------------------
    st.markdown("#### Nivel 2 · Dónde sí hay señal observable")
    st.caption(
        "Como el NPS no discrimina, el cuello de botella se busca en las "
        "señales duras: tiempo de entrega y tasa de envíos fallidos.")

    izquierda, derecha = st.columns(2)
    with izquierda:
        st.plotly_chart(
            theme.grafico_desempeno_logistico(
                resultado.desempeno_ciudad, "Ciudad_Destino",
                "Envíos fallidos por ciudad"), use_container_width=True,
            key="g_p2_fallo_ciudad")
        components.mostrar_veredicto(
            resultado.veredicto_adversa,
            "¿La tasa de fallo se concentra en alguna plaza?")
    with derecha:
        st.plotly_chart(
            theme.grafico_desempeno_logistico(
                resultado.desempeno_bodega, "Bodega_Origen",
                "Envíos fallidos por bodega"), use_container_width=True,
            key="g_p2_fallo_bodega")
        components.mostrar_veredicto(
            resultado.veredicto_tiempo,
            "¿El tiempo de entrega difiere entre plazas?")

    st.markdown("#### Conclusión para la junta")
    st.info(resultado.diagnostico, icon="💡")

    with st.expander("Ver desempeño detallado por plaza y bodega"):
        st.dataframe(resultado.desempeno_ciudad, use_container_width=True,
                     hide_index=True)
        st.dataframe(resultado.desempeno_bodega, use_container_width=True,
                     hide_index=True)


def _seccion_pregunta_3(recorte: pd.DataFrame, diagnostico: dict) -> None:
    """Pregunta 3: análisis de la venta invisible."""
    st.subheader("3 · Análisis de la venta invisible")
    st.markdown(
        "> *Cuantifique el impacto financiero (en USD) de las ventas cuyos "
        "SKU no están en el maestro de inventario. ¿Qué porcentaje del "
        "ingreso total está en riesgo por falta de control de inventario?*")

    resultado = analytics.analizar_venta_invisible(recorte, diagnostico)

    if not resultado.kpis:
        components.aviso_sin_datos(resultado.diagnostico)
        return

    kpis = resultado.kpis
    components.fila_kpis([
        ("Ingreso en riesgo", f"USD {kpis['ingreso_usd']:,.0f}",
         "Ventas cuyo SKU no existe en el maestro de inventario"),
        ("% del ingreso total", f"{kpis['pct_ingreso']:.2f}%",
         "Porción de la facturación sin trazabilidad de costo"),
        ("Productos no catalogados", f"{kpis['skus']:,} SKU",
         f"En {kpis['transacciones']:,} transacciones"),
        ("Utilidad fuera de control",
         f"USD {kpis['margen_no_controlado_usd']:,.0f}",
         f"Estimada aplicando el margen mediano catalogado "
         f"({kpis['margen_mediano_referencia_pct']:.1f}%)"),
    ])

    st.divider()

    izquierda, derecha = st.columns([3, 2])
    with izquierda:
        st.plotly_chart(theme.grafico_fantasma_mensual(resultado.serie_mensual),
                        use_container_width=True, key="g_p3_mensual")
    with derecha:
        st.plotly_chart(
            theme.grafico_fantasma_por_canal(resultado.por_canal),
            use_container_width=True, key="g_p3_canal")

    st.markdown("#### ¿Falla de catálogo o fraude?")
    st.caption(
        "El diccionario de datos plantea el dilema pero no da el criterio. Se "
        "aplican seis pruebas independientes, cada una con una predicción "
        "distinta según la hipótesis. Un error de digitación sobre `PROD-2345` "
        "produciría `PROD-2745`: un valor dentro del rango válido y disperso.")

    if not resultado.criterios_diagnostico.empty:
        st.dataframe(resultado.criterios_diagnostico,
                     use_container_width=True, hide_index=True)

    st.success(f"**Veredicto:** {resultado.veredicto_origen}", icon="🔍")

    st.markdown("#### Conclusión para la junta")
    st.info(resultado.diagnostico, icon="💡")


def renderizar(recorte: pd.DataFrame, descripcion_filtro: str,
               diagnostico_fantasma: dict | None = None) -> None:
    """Dibuja la pestaña de Operaciones.

    Args:
        recorte: SSOT ya filtrada por la selección del usuario.
        descripcion_filtro: Texto legible del recorte aplicado.
        diagnostico_fantasma: Diagnóstico de seis criterios de la Fase 2.
    """
    st.header("Operaciones")
    st.caption(descripcion_filtro)

    if recorte.empty:
        components.aviso_sin_datos()
        return

    _seccion_pregunta_1(recorte)
    st.divider()
    _seccion_pregunta_2(recorte)
    st.divider()
    _seccion_pregunta_3(recorte, diagnostico_fantasma or {})
