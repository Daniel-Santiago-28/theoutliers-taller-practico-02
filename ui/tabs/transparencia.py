"""Pestaña de Transparencia: el antes y el después de la curaduría.

Un consultor senior no limpia datos sin dejar rastro. Aquí se muestra qué
cambió, cuánto mejoró cada dimensión de calidad y —sobre todo— **por qué** se
tomó cada decisión, con la evidencia estadística que la respalda.
"""

from __future__ import annotations

import json

import streamlit as st

from src import config
from src.cleaning import ResultadoLimpieza
from ui import theme

_RENOMBRES_BITACORA = {
    "dataset": "Activo", "columna": "Columna", "accion": "Acción",
    "criterio": "Criterio técnico", "filas_afectadas": "Filas",
    "valor_aplicado": "Valor aplicado",
    "evidencia_estadistica": "Evidencia estadística",
    "justificacion": "Justificación de negocio",
}


def _fila_indicadores(resultado: ResultadoLimpieza) -> None:
    """Indicadores globales del efecto de la limpieza."""
    comparativo = resultado.comparativo()
    total_excluidos = sum(len(f) for f in resultado.registro.excluidos.values())
    mejora_media = comparativo["mejora_pp"].mean()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Mejora promedio", f"+{mejora_media:.1f} pp",
                help="Puntos porcentuales ganados en el Health Score compuesto")
    col2.metric("Filas eliminadas",
                f"{int(comparativo['filas_eliminadas'].sum()):,}",
                help="La política por defecto marca en vez de borrar")
    col3.metric("Registros marcados", f"{total_excluidos:,}",
                help="Excluidos de algún cálculo pero conservados y auditables")
    col4.metric("Decisiones documentadas",
                f"{len(resultado.registro.acciones):,}")


def _seccion_antes_despues(resultado: ResultadoLimpieza) -> None:
    """Comparación visual del Health Score y sus dimensiones."""
    comparativo = resultado.comparativo()

    st.plotly_chart(theme.grafico_dumbbell(comparativo),
                    use_container_width=True)

    dataset = st.selectbox(
        "Ver dimensiones de", list(resultado.crudos),
        format_func=str.capitalize, key="transparencia_dataset")
    st.plotly_chart(theme.grafico_dimensiones(comparativo, dataset),
                    use_container_width=True)

    st.info(
        "**Por qué la completitud puede bajar.** En transacciones cae de "
        "97,5 % a 96,9 %, y es correcto: valores como `Ventas_Web` en la "
        "columna de ciudad o la cantidad `-5` figuraban como datos presentes "
        "cuando en realidad eran ausencias disfrazadas. Convertirlos en nulos "
        "declarados empeora la métrica y mejora la honestidad del dato. Un "
        "Health Score de 100 % obtenido rellenando huecos con la moda sería "
        "una mentira estadística.", icon="ℹ️")

    with st.expander("Ver tabla comparativa completa"):
        st.dataframe(comparativo, use_container_width=True, hide_index=True)


def _seccion_bitacora(resultado: ResultadoLimpieza) -> None:
    """Bitácora de decisiones con su justificación."""
    st.subheader("Bitácora de decisiones de curaduría")
    st.caption(
        "Cada imputación declara el estadístico que la motivó. La estrategia "
        "no se asume: se deriva midiendo la asimetría de cada columna (regla "
        "de Bulmer) y el resultado queda registrado para ser auditado."
    )

    bitacora = resultado.registro.a_dataframe()
    if bitacora.empty:
        st.warning("No hay decisiones registradas.")
        return

    activos = ["(todos)"] + sorted(bitacora["dataset"].unique())
    elegido = st.selectbox("Filtrar por activo", activos,
                           key="transparencia_bitacora")
    vista = bitacora if elegido == "(todos)" \
        else bitacora[bitacora["dataset"] == elegido]

    st.dataframe(
        vista.rename(columns=_RENOMBRES_BITACORA),
        use_container_width=True, hide_index=True,
        column_config={
            "Justificación de negocio": st.column_config.TextColumn(width="large"),
            "Evidencia estadística": st.column_config.TextColumn(width="medium"),
        })


def _seccion_descargas(resultado: ResultadoLimpieza) -> None:
    """Botones de descarga del reporte de limpieza."""
    st.subheader("Descargar el reporte de limpieza")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.download_button(
            "Bitácora de decisiones (CSV)",
            data=resultado.reporte_csv().encode("utf-8-sig"),
            file_name="reporte_limpieza_decisiones.csv", mime="text/csv",
            use_container_width=True)
    with col2:
        st.download_button(
            "Comparativo antes/después (CSV)",
            data=resultado.comparativo_csv().encode("utf-8-sig"),
            file_name="reporte_limpieza_comparativo.csv", mime="text/csv",
            use_container_width=True)
    with col3:
        st.download_button(
            "Reporte completo (JSON)",
            data=json.dumps(resultado.reporte_dict(), ensure_ascii=False,
                            indent=2, default=str).encode("utf-8"),
            file_name="reporte_limpieza.json", mime="application/json",
            use_container_width=True)


def renderizar(resultado: ResultadoLimpieza) -> None:
    """Dibuja la pestaña completa de Transparencia.

    Args:
        resultado: Salida del pipeline de limpieza de la Fase 1.
    """
    st.header("Transparencia del proceso")
    st.markdown(
        f"Toda la curaduría se ejecuta contra una fecha de corte fija "
        f"(**{config.FECHA_CORTE}**) en lugar de la fecha del sistema, de modo "
        f"que los resultados sean reproducibles: los mismos números hoy que en "
        f"cualquier ejecución posterior."
    )

    _fila_indicadores(resultado)
    st.divider()
    _seccion_antes_despues(resultado)
    st.divider()
    _seccion_bitacora(resultado)
    st.divider()
    _seccion_descargas(resultado)
