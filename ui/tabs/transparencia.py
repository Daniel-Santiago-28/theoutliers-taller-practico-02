"""Pestaña de Transparencia: el antes y el después de la curaduría.

Un consultor senior no limpia datos sin dejar rastro. Aquí se muestra qué
cambió, cuánto mejoró cada dimensión de calidad y —sobre todo— **por qué** se
tomó cada decisión, con la evidencia estadística que la respalda.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src import cleaning, config
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
                    use_container_width=True, key="g_transp_dumbbell")

    dataset = st.selectbox(
        "Ver dimensiones de", list(resultado.crudos),
        format_func=str.capitalize, key="transparencia_dataset")
    st.plotly_chart(theme.grafico_dimensiones(comparativo, dataset),
                    use_container_width=True, key="g_transp_dimensiones")

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


def _seccion_trazabilidad(resultado: ResultadoLimpieza) -> None:
    """Inventario de banderas: qué valores son estimados y cuáles observados."""
    st.subheader("Trazabilidad a nivel de fila")
    st.caption(
        "Cada corrección deja una bandera booleana en la propia fila, no solo "
        "una línea en la bitácora. Así un valor estimado nunca queda "
        "indistinguible de uno observado y el análisis puede excluirlo cuando "
        "mida dispersión o correlación."
    )

    filas = []
    for nombre, df in resultado.limpios.items():
        for columna in df.columns:
            if str(df[columna].dtype) not in {"bool", "boolean"}:
                continue
            if columna in config.ESQUEMAS[nombre]:
                continue  # es un dato del negocio, no una bandera de curaduría
            filas.append({
                "Activo": nombre,
                "Bandera": columna,
                "Filas marcadas": int(df[columna].sum()),
                "% del activo": round(100 * float(df[columna].mean()), 2),
            })

    if not filas:
        st.info("No hay banderas de trazabilidad.")
        return

    tabla = pd.DataFrame(filas).sort_values(
        ["Activo", "Filas marcadas"], ascending=[True, False])
    st.dataframe(tabla, use_container_width=True, hide_index=True)

    imputadas = tabla[tabla["Bandera"].str.endswith(cleaning.SUFIJO_IMPUTADO)]
    if not imputadas.empty:
        st.warning(
            f"**{int(imputadas['Filas marcadas'].sum()):,} valores son "
            f"estimados, no observados.** La imputación por media fija esos "
            f"registros en el centro exacto de la distribución, lo que contrae "
            f"la varianza y atenúa cualquier correlación que los incluya. "
            f"Para análisis de dispersión o correlación, filtre por la bandera "
            f"correspondiente.", icon="⚠️")


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
        f"La validación temporal se ejecuta contra la fecha del sistema "
        f"(**{config.fecha_corte()}**): una venta registrada después de ese "
        f"instante es un error de captura del sistema origen. Los conteos "
        f"temporales de esta pestaña deben citarse siempre junto a la fecha en "
        f"que se generaron."
    )
    st.caption(
        "**Alcance:** igual que Auditoría, esta pestaña ignora los filtros del "
        "panel lateral. Documenta el proceso de curaduría completo, que se "
        "ejecutó una única vez sobre los tres archivos fuente. Los filtros "
        "actúan sobre las pestañas de negocio.")

    _fila_indicadores(resultado)
    st.divider()
    _seccion_antes_despues(resultado)
    st.divider()
    _seccion_bitacora(resultado)
    st.divider()
    _seccion_trazabilidad(resultado)
    st.divider()
    _seccion_descargas(resultado)
