"""Tokens de diseño y helpers de gráficos del dashboard.

Centraliza la paleta para que ninguna pestaña invente colores. Los tonos son
los slots 1 y 2 de una paleta categórica validada para daltonismo en modo
claro y oscuro; el orden de los slots es el mecanismo de seguridad, no una
decisión estética, así que no debe reordenarse al agregar series.

Las gráficas usan fondo transparente y tinta 'muted', que es idéntica en
ambos modos: así heredan el tema claro u oscuro que tenga activo Streamlit
sin necesidad de detectarlo.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# --- Paleta categórica (no reordenar) ------------------------------------
SERIE_ANTES = "#eb6834"      # slot 2, naranja
SERIE_DESPUES = "#2a78d6"    # slot 1, azul
SECUENCIAL = "#2a78d6"

# Alias semánticos sobre los mismos dos slots validados. El color sigue a la
# entidad —rentable o deficitario— y nunca al ranking, de modo que aplicar un
# filtro no repinte las series que sobreviven.
SERIE_RENTABLE = "#2a78d6"
SERIE_DEFICITARIA = "#eb6834"

# --- Estado (nunca se reutiliza para series) ------------------------------
ESTADO_BUENO = "#0ca30c"
ESTADO_ALERTA = "#fab219"
ESTADO_GRAVE = "#ec835a"
ESTADO_CRITICO = "#d03b3b"

# --- Tinta y cromo --------------------------------------------------------
TINTA_MUTED = "#898781"      # idéntica en claro y oscuro
LINEA_REJILLA = "rgba(137,135,129,0.25)"

FUENTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def clasificar_score(score: float) -> tuple[str, str, str]:
    """Traduce un Health Score a banda de estado.

    El color de estado nunca viaja solo: se devuelve junto con un ícono y una
    etiqueta, de modo que la señal no dependa únicamente del color.

    Returns:
        Tupla (color, ícono, etiqueta).
    """
    if score >= 95:
        return ESTADO_BUENO, "●", "Saludable"
    if score >= 85:
        return ESTADO_ALERTA, "▲", "Aceptable"
    if score >= 70:
        return ESTADO_GRAVE, "▲", "Deficiente"
    return ESTADO_CRITICO, "■", "Crítico"


def _aplicar_estilo(fig: go.Figure, alto: int = 320) -> go.Figure:
    """Aplica el cromo común: fondo transparente, rejilla tenue, sin ruido."""
    fig.update_layout(
        height=alto,
        margin=dict(l=8, r=8, t=48, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FUENTE, color=TINTA_MUTED, size=13),
        hoverlabel=dict(font_family=FUENTE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, title=None),
    )
    fig.update_xaxes(gridcolor=LINEA_REJILLA, zeroline=False,
                     linecolor=LINEA_REJILLA)
    fig.update_yaxes(gridcolor=LINEA_REJILLA, zeroline=False,
                     linecolor=LINEA_REJILLA)
    return fig


def grafico_dumbbell(
    comparativo: pd.DataFrame, titulo: str = "Health Score: antes y después",
) -> go.Figure:
    """Gráfico de mancuerna del cambio de Health Score por dataset.

    La mancuerna es la forma correcta aquí: el dato a leer es la *magnitud del
    cambio* entre dos estados, y el segmento la codifica como longitud, que se
    compara mucho mejor que dos barras separadas.
    """
    df = comparativo.sort_values("health_score_despues")
    fig = go.Figure()

    for _, fila in df.iterrows():
        fig.add_trace(go.Scatter(
            x=[fila["health_score_antes"], fila["health_score_despues"]],
            y=[fila["dataset"], fila["dataset"]],
            mode="lines", line=dict(color=TINTA_MUTED, width=2),
            hoverinfo="skip", showlegend=False,
        ))

    for etiqueta, columna, color in (
        ("Antes", "health_score_antes", SERIE_ANTES),
        ("Después", "health_score_despues", SERIE_DESPUES),
    ):
        fig.add_trace(go.Scatter(
            x=df[columna], y=df["dataset"], mode="markers+text",
            name=etiqueta,
            marker=dict(size=15, color=color,
                        line=dict(color="rgba(255,255,255,0.9)", width=2)),
            text=[f"{v:.1f}" for v in df[columna]],
            textposition="top center" if etiqueta == "Antes" else "bottom center",
            textfont=dict(color=TINTA_MUTED, size=12),
            hovertemplate=f"<b>%{{y}}</b><br>{etiqueta}: %{{x:.2f}}/100"
                          "<extra></extra>",
        ))

    fig.update_layout(title=titulo, xaxis_title="Health Score (0-100)")
    fig.update_xaxes(range=[max(0, df["health_score_antes"].min() - 12), 104])
    return _aplicar_estilo(fig, alto=300)


def grafico_dimensiones(
    comparativo: pd.DataFrame, dataset: str,
    dimensiones: tuple[str, ...] = ("completitud", "validez", "unicidad",
                                    "consistencia"),
) -> go.Figure:
    """Barras agrupadas de las cuatro dimensiones de calidad, antes y después."""
    fila = comparativo.loc[comparativo["dataset"] == dataset].iloc[0]
    etiquetas = [d.capitalize() for d in dimensiones]

    fig = go.Figure()
    for nombre, sufijo, color in (("Antes", "antes", SERIE_ANTES),
                                  ("Después", "despues", SERIE_DESPUES)):
        valores = [fila[f"{d}_{sufijo}"] for d in dimensiones]
        fig.add_trace(go.Bar(
            name=nombre, x=etiquetas, y=valores, marker_color=color,
            marker_line=dict(width=2, color="rgba(0,0,0,0)"),
            text=[f"{v:.1f}" for v in valores], textposition="outside",
            textfont=dict(color=TINTA_MUTED, size=11),
            hovertemplate=f"<b>%{{x}}</b><br>{nombre}: %{{y:.2f}}%"
                          "<extra></extra>",
        ))

    fig.update_layout(
        title=f"Dimensiones de calidad · {dataset}",
        barmode="group", bargap=0.35, bargroupgap=0.08,
        yaxis_title="% de cumplimiento", yaxis_range=[0, 112],
    )
    return _aplicar_estilo(fig, alto=340)


def grafico_nulidad(perfil: pd.DataFrame, titulo: str) -> go.Figure:
    """Barras horizontales del porcentaje de ausencia por columna.

    Una sola serie: no lleva leyenda, el título la nombra.
    """
    df = perfil.sort_values("pct_ausentes")
    fig = go.Figure(go.Bar(
        x=df["pct_ausentes"], y=df["columna"], orientation="h",
        marker_color=SECUENCIAL,
        marker_line=dict(width=2, color="rgba(0,0,0,0)"),
        text=[f"{v:.1f}%" if v > 0 else "" for v in df["pct_ausentes"]],
        textposition="outside", textfont=dict(color=TINTA_MUTED, size=11),
        hovertemplate="<b>%{y}</b><br>%{x:.2f}% ausente<extra></extra>",
    ))
    fig.update_layout(title=titulo, xaxis_title="% de ausencia real",
                      showlegend=False)
    fig.update_xaxes(range=[0, max(5, df["pct_ausentes"].max() * 1.25)])
    return _aplicar_estilo(fig, alto=max(260, 30 * len(df)))


# --------------------------------------------------------------------------
# Pregunta 1: fuga de capital
# --------------------------------------------------------------------------


def grafico_costo_vs_precio(por_sku: pd.DataFrame) -> go.Figure:
    """Dispersión de costo contra precio, con la diagonal de equilibrio.

    Es la gráfica que responde el *porqué* de la pregunta 1. Si existiera una
    política de precios, los puntos formarían una banda ascendente por encima
    de la diagonal. Una nube sin pendiente significa que el precio se fija sin
    mirar el costo, y todo lo que cae bajo la diagonal se vende con pérdida.
    """
    fig = go.Figure()

    limite = float(max(por_sku["costo_unitario_usd"].max(),
                       por_sku["precio_medio_usd"].max())) * 1.02

    # Umbral de equilibrio: por debajo, el precio no cubre el costo.
    fig.add_trace(go.Scatter(
        x=[0, limite], y=[0, limite], mode="lines", name="Punto de equilibrio",
        line=dict(color=TINTA_MUTED, width=2, dash="dash"),
        hovertemplate="Precio = Costo<extra></extra>"))

    for etiqueta, deficitario, color in (
        ("Rentable", False, SERIE_RENTABLE),
        ("Deficitario", True, SERIE_DEFICITARIA),
    ):
        grupo = por_sku[por_sku["Es_Deficitario"] == deficitario]
        fig.add_trace(go.Scatter(
            x=grupo["costo_unitario_usd"], y=grupo["precio_medio_usd"],
            mode="markers", name=etiqueta,
            marker=dict(size=7, color=color, opacity=0.55,
                        line=dict(width=0)),
            customdata=grupo[["SKU_ID", "margen_neto_usd", "unidades"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Costo: USD %{x:,.2f}<br>"
                "Precio medio: USD %{y:,.2f}<br>"
                "Margen neto: USD %{customdata[1]:,.2f}<br>"
                "Unidades: %{customdata[2]:,.0f}<extra></extra>")))

    fig.update_layout(
        title="Precio de venta frente a costo unitario, por SKU",
        xaxis_title="Costo unitario (USD)",
        yaxis_title="Precio medio de venta (USD)")
    return _aplicar_estilo(fig, alto=420)


def grafico_tasa_por_canal(por_canal: pd.DataFrame) -> go.Figure:
    """Tasa de margen negativo por canal de venta.

    Una sola serie: el título la nombra y no lleva leyenda. El canal Online se
    resalta porque es el que la junta señala como sospechoso en la pregunta.
    """
    df = por_canal.sort_values("tasa_negativa_pct")
    colores = [SERIE_DEFICITARIA if canal == "Online" else TINTA_MUTED
               for canal in df["Canal_Venta"]]

    fig = go.Figure(go.Bar(
        x=df["tasa_negativa_pct"], y=df["Canal_Venta"], orientation="h",
        marker_color=colores, marker_line=dict(width=2, color="rgba(0,0,0,0)"),
        text=[f"{v:.1f}%" for v in df["tasa_negativa_pct"]],
        textposition="outside", textfont=dict(color=TINTA_MUTED, size=12),
        customdata=df[["perdida_usd", "transacciones"]],
        hovertemplate=("<b>%{y}</b><br>%{x:.2f}% de ventas deficitarias<br>"
                       "Pérdida: USD %{customdata[0]:,.0f}<br>"
                       "Transacciones: %{customdata[1]:,}<extra></extra>")))

    fig.update_layout(
        title="Ventas con margen negativo por canal (Online resaltado)",
        xaxis_title="% de transacciones deficitarias", showlegend=False)
    fig.update_xaxes(range=[0, max(50, df["tasa_negativa_pct"].max() * 1.25)])
    return _aplicar_estilo(fig, alto=300)


def grafico_pareto_perdida(pareto: pd.DataFrame) -> go.Figure:
    """Concentración acumulada de la pérdida sobre los SKU deficitarios.

    La diagonal de referencia representa una pérdida perfectamente repartida.
    Cuanto más se pegue la curva a esa diagonal, menos sirve corregir SKU por
    SKU y más claro queda que el problema es de proceso.
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=[0, 100], y=[0, 100], mode="lines", name="Pérdida uniforme",
        line=dict(color=TINTA_MUTED, width=2, dash="dash"),
        hoverinfo="skip"))

    fig.add_trace(go.Scatter(
        x=pareto["pct_skus"], y=pareto["pct_perdida"], mode="lines",
        name="Pérdida observada",
        line=dict(color=SERIE_DEFICITARIA, width=2),
        hovertemplate=("%{x:.1f}% de los SKU deficitarios<br>"
                       "acumulan %{y:.1f}% de la pérdida<extra></extra>")))

    fig.update_layout(
        title="¿La pérdida se concentra en unos pocos productos?",
        xaxis_title="% de SKU deficitarios (ordenados de peor a mejor)",
        yaxis_title="% de la pérdida acumulada")
    fig.update_xaxes(range=[0, 100])
    fig.update_yaxes(range=[0, 100])
    return _aplicar_estilo(fig, alto=380)


def grafico_volumen_vs_margen(por_sku: pd.DataFrame) -> go.Figure:
    """Volumen vendido frente a margen unitario, por SKU.

    Contrasta la hipótesis del producto gancho. Si la pérdida fuera una
    estrategia deliberada, los SKU de mayor volumen se agruparían en la franja
    inferior. Una nube plana significa que se pierde dinero sin comprar
    tráfico a cambio.
    """
    fig = go.Figure()

    fig.add_hline(y=0, line=dict(color=TINTA_MUTED, width=2, dash="dash"))

    for etiqueta, deficitario, color in (
        ("Rentable", False, SERIE_RENTABLE),
        ("Deficitario", True, SERIE_DEFICITARIA),
    ):
        grupo = por_sku[por_sku["Es_Deficitario"] == deficitario]
        fig.add_trace(go.Scatter(
            x=grupo["unidades"], y=grupo["margen_unitario_usd"],
            mode="markers", name=etiqueta,
            marker=dict(size=7, color=color, opacity=0.55,
                        line=dict(width=0)),
            customdata=grupo[["SKU_ID", "margen_neto_usd"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Unidades: %{x:,.0f}<br>"
                "Margen unitario: USD %{y:,.2f}<br>"
                "Margen neto: USD %{customdata[1]:,.2f}<extra></extra>")))

    fig.update_layout(
        title="Volumen vendido frente a margen unitario, por SKU",
        xaxis_title="Unidades vendidas",
        yaxis_title="Margen unitario medio (USD)")
    return _aplicar_estilo(fig, alto=380)


# --------------------------------------------------------------------------
# Pregunta 2: crisis logística
# --------------------------------------------------------------------------


def grafico_correlaciones(correlaciones: pd.DataFrame, dimension: str,
                          titulo: str) -> go.Figure:
    """Ranking de correlaciones con las no significativas atenuadas.

    Es la gráfica que el enunciado pide, presentada de forma que no engañe:
    las barras que no sobreviven a la corrección de Bonferroni se dibujan en
    gris de fondo, de modo que el ojo no lea como hallazgo lo que es ruido de
    muestreo. Si ninguna sobrevive, toda la gráfica queda gris y esa es
    justamente la conclusión.
    """
    if correlaciones.empty:
        return _figura_vacia("Sin grupos con muestra suficiente")

    df = correlaciones.sort_values("rho")
    colores = [SERIE_DEFICITARIA if sig else "rgba(137,135,129,0.35)"
               for sig in df["significativo"]]

    fig = go.Figure(go.Bar(
        x=df["rho"], y=df[dimension].astype(str), orientation="h",
        marker_color=colores, marker_line=dict(width=2, color="rgba(0,0,0,0)"),
        text=[f"ρ={v:.3f}" for v in df["rho"]],
        textposition="outside", textfont=dict(color=TINTA_MUTED, size=11),
        customdata=df[["n", "p_crudo", "p_corregido"]],
        hovertemplate=("<b>%{y}</b><br>rho = %{x:.4f}<br>n = %{customdata[0]}"
                       "<br>p sin corregir = %{customdata[1]:.4f}<br>"
                       "p con Bonferroni = %{customdata[2]:.4f}"
                       "<extra></extra>")))

    fig.add_vline(x=0, line=dict(color=TINTA_MUTED, width=2))
    limite = max(0.15, float(df["rho"].abs().max()) * 1.6)
    fig.update_layout(title=titulo,
                      xaxis_title="rho de Spearman (demora vs NPS)",
                      showlegend=False)
    fig.update_xaxes(range=[-limite, limite])
    return _aplicar_estilo(fig, alto=max(260, 46 * len(df)))


def grafico_desempeno_logistico(desempeno: pd.DataFrame, dimension: str,
                                titulo: str) -> go.Figure:
    """Tasa de envíos en estado adverso por plaza o bodega.

    Una sola serie y una línea de referencia con el promedio global: lo que
    importa no es cuál barra es más larga, sino que todas estén igual de
    altas.
    """
    if desempeno.empty:
        return _figura_vacia("Sin datos para esta dimensión")

    df = desempeno.sort_values("tasa_adversa")
    promedio = float(df["tasa_adversa"].mean())

    fig = go.Figure(go.Bar(
        x=df["tasa_adversa"], y=df[dimension].astype(str), orientation="h",
        marker_color=SECUENCIAL, marker_line=dict(width=2,
                                                  color="rgba(0,0,0,0)"),
        text=[f"{v:.1f}%" for v in df["tasa_adversa"]],
        textposition="outside", textfont=dict(color=TINTA_MUTED, size=11),
        customdata=df[["transacciones", "entrega_mediana", "entrega_p90"]],
        hovertemplate=("<b>%{y}</b><br>%{x:.2f}% en estado adverso<br>"
                       "Transacciones: %{customdata[0]:,}<br>"
                       "Entrega mediana: %{customdata[1]:.0f} días<br>"
                       "Percentil 90: %{customdata[2]:.0f} días"
                       "<extra></extra>")))

    fig.add_vline(x=promedio, line=dict(color=TINTA_MUTED, width=2,
                                        dash="dash"),
                  annotation_text=f"promedio {promedio:.1f}%",
                  annotation_font=dict(color=TINTA_MUTED, size=11))

    fig.update_layout(title=titulo,
                      xaxis_title="% de envíos retrasados, perdidos o devueltos",
                      showlegend=False)
    fig.update_xaxes(range=[0, max(70, float(df["tasa_adversa"].max()) * 1.25)])
    return _aplicar_estilo(fig, alto=max(260, 46 * len(df)))


# --------------------------------------------------------------------------
# Pregunta 3: venta invisible
# --------------------------------------------------------------------------


def grafico_fantasma_mensual(serie: pd.DataFrame) -> go.Figure:
    """Participación mensual del ingreso sin catálogo.

    Una línea plana significa fuga estructural; un pico aislado significaría
    un incidente puntual de carga. La distinción cambia por completo la
    recomendación.
    """
    if serie.empty:
        return _figura_vacia("Sin serie temporal para el filtro aplicado")

    promedio = float(serie["pct_fantasma"].mean())

    fig = go.Figure(go.Scatter(
        x=serie["mes"], y=serie["pct_fantasma"], mode="lines+markers",
        name="% del ingreso sin catálogo",
        line=dict(color=SERIE_DEFICITARIA, width=2),
        marker=dict(size=8, color=SERIE_DEFICITARIA,
                    line=dict(color="rgba(255,255,255,0.9)", width=2)),
        customdata=serie[["ingreso_fantasma", "ingreso_total"]],
        hovertemplate=("<b>%{x}</b><br>%{y:.2f}% del ingreso<br>"
                       "Sin catálogo: USD %{customdata[0]:,.0f}<br>"
                       "Total del mes: USD %{customdata[1]:,.0f}"
                       "<extra></extra>")))

    fig.add_hline(y=promedio, line=dict(color=TINTA_MUTED, width=2,
                                        dash="dash"),
                  annotation_text=f"promedio {promedio:.1f}%",
                  annotation_font=dict(color=TINTA_MUTED, size=11))

    fig.update_layout(
        title="Participación mensual del ingreso sin catálogo oficial",
        xaxis_title=None, yaxis_title="% del ingreso del mes",
        showlegend=False)
    fig.update_yaxes(range=[0, max(30, float(serie["pct_fantasma"].max()) * 1.3)])
    return _aplicar_estilo(fig, alto=340)


def grafico_fantasma_por_canal(por_canal: pd.DataFrame) -> go.Figure:
    """Ingreso invisible por canal, en valor absoluto.

    Si la fuga se concentrara en un canal, apuntaría a una integración rota.
    Un reparto parejo apunta a que el catálogo maestro es el eslabón que
    falla, no un sistema de venta concreto.
    """
    if por_canal.empty:
        return _figura_vacia("Sin datos por canal")

    df = por_canal.sort_values("ingreso_fantasma")

    fig = go.Figure(go.Bar(
        x=df["ingreso_fantasma"], y=df["Canal_Venta"].astype(str),
        orientation="h", marker_color=SERIE_DEFICITARIA,
        marker_line=dict(width=2, color="rgba(0,0,0,0)"),
        text=[f"USD {v:,.0f}" for v in df["ingreso_fantasma"]],
        textposition="outside", textfont=dict(color=TINTA_MUTED, size=11),
        customdata=df[["pct_fantasma", "trx_fantasma"]],
        hovertemplate=("<b>%{y}</b><br>USD %{x:,.0f} sin catálogo<br>"
                       "%{customdata[0]:.2f}% del ingreso del canal<br>"
                       "%{customdata[1]:,} transacciones<extra></extra>")))

    fig.update_layout(title="Ingreso sin catálogo por canal de venta",
                      xaxis_title="USD", showlegend=False)
    fig.update_xaxes(range=[0, float(df["ingreso_fantasma"].max()) * 1.35])
    return _aplicar_estilo(fig, alto=300)


# --------------------------------------------------------------------------
# Pregunta 4: paradoja de fidelidad
# --------------------------------------------------------------------------


def grafico_paradoja(por_categoria: pd.DataFrame) -> go.Figure:
    """Stock medio frente a calificación de producto, por categoría.

    El cuadrante superior izquierdo —mucho inventario, clientes molestos— es
    donde viviría la paradoja que plantea la pregunta. Las líneas de
    referencia marcan la media de cada eje; si todas las categorías se
    apiñan alrededor del cruce, la paradoja no existe.
    """
    if por_categoria.empty:
        return _figura_vacia("Sin categorías para el filtro aplicado")

    df = por_categoria.dropna(subset=["stock_medio", "rating_producto"])
    if df.empty:
        return _figura_vacia("Sin calificaciones para estas categorías")

    fig = go.Figure(go.Scatter(
        x=df["rating_producto"], y=df["stock_medio"], mode="markers+text",
        text=df["Categoria_Analisis"], textposition="top center",
        textfont=dict(color=TINTA_MUTED, size=11),
        marker=dict(size=16, color=SECUENCIAL,
                    line=dict(color="rgba(255,255,255,0.9)", width=2)),
        customdata=df[["transacciones", "tasa_tickets", "margen_mediano_pct"]],
        hovertemplate=("<b>%{text}</b><br>Rating medio: %{x:.2f}/5<br>"
                       "Stock medio: %{y:,.0f} unidades<br>"
                       "Transacciones: %{customdata[0]:,}<br>"
                       "Tasa de tickets: %{customdata[1]:.1f}%<br>"
                       "Margen mediano: %{customdata[2]:.1f}%"
                       "<extra></extra>")))

    fig.add_vline(x=float(df["rating_producto"].mean()),
                  line=dict(color=TINTA_MUTED, width=2, dash="dash"))
    fig.add_hline(y=float(df["stock_medio"].mean()),
                  line=dict(color=TINTA_MUTED, width=2, dash="dash"))

    fig.update_layout(
        title="Disponibilidad frente a satisfacción, por categoría",
        xaxis_title="Calificación media de producto (1-5)",
        yaxis_title="Stock medio (unidades)", showlegend=False)
    return _aplicar_estilo(fig, alto=420)


def grafico_causa_raiz(causa_raiz: pd.DataFrame) -> go.Figure:
    """Reparto del motivo de queja dentro de cada categoría.

    Barras apiladas al 100 %: lo que se compara es la *composición* del
    reclamo, no su volumen. Responde directamente la disyuntiva de la
    pregunta entre mala calidad y sobrecosto.
    """
    if causa_raiz.empty:
        return _figura_vacia("Sin comentarios con causa identificable")

    llave = causa_raiz.columns[0]
    causas = [c for c in causa_raiz.columns if c != llave and c != "Ninguna"]
    # Orden fijo de hues: el color sigue a la causa, nunca a su tamaño.
    paleta = {"Calidad": "#2a78d6", "Logística": "#eb6834",
              "Precio/Valor": "#1baf7a", "Ninguna": "rgba(137,135,129,0.35)"}

    fig = go.Figure()
    for causa in causas + (["Ninguna"] if "Ninguna" in causa_raiz.columns
                           else []):
        fig.add_trace(go.Bar(
            name=causa, y=causa_raiz[llave].astype(str),
            x=causa_raiz[causa], orientation="h",
            marker_color=paleta.get(causa, TINTA_MUTED),
            marker_line=dict(width=2, color="rgba(0,0,0,0)"),
            hovertemplate=f"<b>%{{y}}</b><br>{causa}: %{{x:.1f}}%"
                          "<extra></extra>"))

    fig.update_layout(
        title="Motivo del reclamo por categoría (composición)",
        barmode="stack", xaxis_title="% de los comentarios de la categoría")
    fig.update_xaxes(range=[0, 100])
    return _aplicar_estilo(fig, alto=max(300, 52 * len(causa_raiz)))


# --------------------------------------------------------------------------
# Pregunta 5: riesgo operativo
# --------------------------------------------------------------------------


def grafico_antiguedad_vs_tickets(por_bodega: pd.DataFrame) -> go.Figure:
    """Antigüedad del conteo físico frente a la tasa de reclamos, por bodega.

    Las bodegas sin nomenclatura regional se marcan con símbolo distinto, no
    solo con color: son las candidatas naturales a operar sin supervisión y
    conviene poder ubicarlas sin depender del tono.
    """
    if por_bodega.empty:
        return _figura_vacia("Sin bodegas para el filtro aplicado")

    fig = go.Figure()
    for etiqueta, no_estandar, simbolo, color in (
        ("Bodega regional", False, "circle", SECUENCIAL),
        ("Nomenclatura no estándar", True, "diamond", SERIE_DEFICITARIA),
    ):
        grupo = por_bodega[por_bodega["Nomenclatura_No_Estandar"]
                           == no_estandar]
        if grupo.empty:
            continue
        fig.add_trace(go.Scatter(
            x=grupo["antiguedad_mediana"], y=grupo["tasa_tickets"],
            mode="markers+text", name=etiqueta,
            text=grupo["Bodega_Origen"], textposition="top center",
            textfont=dict(color=TINTA_MUTED, size=11),
            marker=dict(size=16, color=color, symbol=simbolo,
                        line=dict(color="rgba(255,255,255,0.9)", width=2)),
            customdata=grupo[["transacciones", "tasa_bajo_reorden"]],
            hovertemplate=("<b>%{text}</b><br>Antigüedad: %{x:.0f} días<br>"
                           "Tasa de tickets: %{y:.2f}%<br>"
                           "Transacciones: %{customdata[0]:,}<br>"
                           "Bajo punto de reorden: %{customdata[1]:.1f}%"
                           "<extra></extra>")))

    fig.update_layout(
        title="Antigüedad del conteo físico frente a carga de soporte",
        xaxis_title="Días desde el último conteo físico (mediana)",
        yaxis_title="% de ventas con ticket de soporte")
    return _aplicar_estilo(fig, alto=400)


def grafico_antiguedad_bodega(por_bodega: pd.DataFrame) -> go.Figure:
    """Meses sin conteo físico por bodega, con umbral de referencia."""
    if por_bodega.empty:
        return _figura_vacia("Sin bodegas para el filtro aplicado")

    df = por_bodega.sort_values("antiguedad_mediana")
    meses = df["antiguedad_mediana"] / 30.4

    fig = go.Figure(go.Bar(
        x=meses, y=df["Bodega_Origen"].astype(str), orientation="h",
        marker_color=SERIE_DEFICITARIA,
        marker_line=dict(width=2, color="rgba(0,0,0,0)"),
        text=[f"{v:.1f} meses" for v in meses],
        textposition="outside", textfont=dict(color=TINTA_MUTED, size=11),
        customdata=df[["antiguedad_mediana", "tasa_bajo_reorden"]],
        hovertemplate=("<b>%{y}</b><br>%{customdata[0]:.0f} días sin conteo"
                       "<br>Bajo punto de reorden: %{customdata[1]:.1f}%"
                       "<extra></extra>")))

    # Doce meses es el ciclo anual mínimo de un inventario físico auditable.
    fig.add_vline(x=12, line=dict(color=TINTA_MUTED, width=2, dash="dash"),
                  annotation_text="ciclo anual",
                  annotation_font=dict(color=TINTA_MUTED, size=11))

    fig.update_layout(title="Tiempo sin verificación física del inventario",
                      xaxis_title="Meses desde el último conteo",
                      showlegend=False)
    fig.update_xaxes(range=[0, float(meses.max()) * 1.3])
    return _aplicar_estilo(fig, alto=max(260, 46 * len(df)))


def _figura_vacia(mensaje: str) -> go.Figure:
    """Marcador de posición cuando el filtro no deja datos que graficar."""
    fig = go.Figure()
    fig.add_annotation(text=mensaje, showarrow=False,
                       font=dict(color=TINTA_MUTED, size=14))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _aplicar_estilo(fig, alto=240)
