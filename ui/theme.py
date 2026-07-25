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
