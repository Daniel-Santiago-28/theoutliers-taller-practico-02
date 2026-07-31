"""Pestaña de Visión General: cifras agregadas de la operación filtrada.

Es la puerta de entrada del dashboard: solo indicadores, sin veredictos
estadísticos ni gráficas de detalle (esas viven en Operaciones, Cliente e
Insights de IA). Recibe el recorte igual que esas tres pestañas, así que
responde tanto a los filtros del panel lateral como al interruptor
"Incluir venta sin catálogo".
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import analytics
from ui import components


def renderizar(recorte: pd.DataFrame, descripcion_filtro: str) -> None:
    """Dibuja la pestaña de Visión General.

    Args:
        recorte: SSOT ya filtrada por la selección del usuario.
        descripcion_filtro: Texto legible del recorte aplicado.
    """
    st.header("Visión general")
    st.caption(descripcion_filtro)

    if recorte.empty:
        components.aviso_sin_datos()
        return

    resultado = analytics.analizar_resumen_general(recorte)
    kpis = resultado.kpis

    st.markdown("#### Rentabilidad")
    components.fila_kpis([
        ("Ingreso total", f"USD {kpis['ingreso_total_usd']:,.0f}",
         "Precio_Venta_Final × Cantidad_Vendida, sumado sobre el recorte"),
        ("Costo de mercancía", f"USD {kpis['costo_mercancia_usd']:,.0f}",
         "Solo transacciones con costo conocido"),
        ("Margen neto total", f"USD {kpis['margen_neto_total_usd']:,.0f}",
         "Ingreso − costo de mercancía − costo de envío, donde hay costo "
         "conocido"),
        ("Margen %", f"{kpis['margen_pct_agregado']:.1f}%",
         "Margen neto total / ingreso total"),
    ])

    st.markdown("#### Operación")
    components.fila_kpis([
        ("Transacciones", f"{kpis['transacciones']:,}",
         "Filas del recorte actual"),
        ("Unidades vendidas", f"{kpis['unidades_vendidas']:,}",
         "Suma de Cantidad_Vendida"),
        ("Ticket promedio", f"USD {kpis['ticket_promedio_usd']:,.0f}",
         "Ingreso total / transacciones"),
        ("SKU distintos", f"{kpis['skus_distintos']:,}",
         "Productos distintos con al menos una venta en el recorte"),
    ])

    for advertencia in resultado.advertencias:
        st.caption(f"ℹ️ {advertencia}")
