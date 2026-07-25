"""Pestaña de Auditoría: calidad de los datos crudos y registros excluidos.

Responde a la pregunta "¿qué tan confiables son estos datos?" antes de que el
usuario mire un solo KPI de negocio. Esta pestaña solo presenta: todo el
cálculo vive en ``src.audit`` y ``src.cleaning``.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import audit
from src.cleaning import ResultadoLimpieza
from ui import theme


def _tarjetas_score(resultado: ResultadoLimpieza, momento: str) -> None:
    """Fila de tarjetas con el Health Score de cada activo."""
    scores = (resultado.scores_antes if momento == "antes"
              else resultado.scores_despues)
    columnas = st.columns(len(scores))

    for columna, (nombre, score) in zip(columnas, scores.items()):
        color, icono, etiqueta = theme.clasificar_score(score.total)
        with columna:
            st.metric(label=nombre.capitalize(), value=f"{score.total:.1f}/100")
            # El color de estado siempre viaja con ícono y etiqueta: la señal
            # nunca depende únicamente del color.
            st.markdown(
                f"<span style='color:{color};font-weight:600'>{icono} "
                f"{etiqueta}</span>", unsafe_allow_html=True)


def _seccion_perfil_calidad(resultado: ResultadoLimpieza) -> None:
    """Nulidad por columna y reglas de negocio violadas en los datos crudos."""
    st.subheader("Perfil de calidad de los datos crudos")
    st.caption(
        "La ausencia se mide contando también los centinelas de texto "
        "('???', 'nan', 'N/A', '---'). Contar solo los nulos técnicos "
        "subestimaría el problema y haría ver el archivo mejor de lo que está."
    )

    dataset = st.selectbox(
        "Activo de información", list(resultado.crudos),
        format_func=str.capitalize, key="auditoria_dataset")

    izquierda, derecha = st.columns([1, 1])

    with izquierda:
        perfil = audit.perfil_nulidad(resultado.crudos[dataset])
        st.plotly_chart(
            theme.grafico_nulidad(perfil, f"Ausencia por columna · {dataset}"),
            use_container_width=True)

    with derecha:
        st.markdown("**Reglas de negocio violadas**")
        violadas = (resultado.scores_antes[dataset]
                    .dimensiones["validez"].detalle["reglas_violadas"])
        if not violadas:
            st.success("Ninguna regla de validez violada en este activo.")
        else:
            tabla = pd.DataFrame(violadas).rename(columns={
                "columna": "Columna", "regla": "Regla incumplida",
                "violaciones": "Registros", "pct": "% del total"})
            st.dataframe(tabla, use_container_width=True, hide_index=True)

        inconsistentes = (resultado.scores_antes[dataset]
                          .dimensiones["consistencia"]
                          .detalle["columnas_inconsistentes"])
        if inconsistentes:
            st.markdown("**Categóricas sin forma canónica**")
            for item in inconsistentes:
                variantes = ", ".join(
                    f"`{k}` ({v:,})" for k, v in item["variantes"].items())
                st.markdown(
                    f"- **{item['columna']}**: {item['valores_no_canonicos']:,} "
                    f"valores no canónicos → {variantes}")


def _seccion_excluidos(resultado: ResultadoLimpieza) -> None:
    """Visor de registros excluidos: nada se descarta en silencio."""
    st.subheader("Registros excluidos")
    st.caption(
        "Ningún registro se elimina en silencio. Todo lo que quedó fuera de "
        "un cálculo permanece aquí, consultable y descargable."
    )

    excluidos = resultado.registro.excluidos
    if not excluidos:
        st.info("No se excluyó ningún registro.")
        return

    etiquetas = {
        clave: f"{clave.replace('_', ' ').capitalize()} ({len(frame):,})"
        for clave, frame in excluidos.items()
    }
    seleccion = st.selectbox(
        "Motivo de exclusión", list(excluidos),
        format_func=lambda c: etiquetas[c], key="auditoria_excluidos")

    frame = excluidos[seleccion]
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.download_button(
        f"Descargar registros excluidos ({len(frame):,})",
        data=frame.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"excluidos_{seleccion}.csv", mime="text/csv",
        key="descarga_excluidos")


def renderizar(resultado: ResultadoLimpieza) -> None:
    """Dibuja la pestaña completa de Auditoría.

    Args:
        resultado: Salida del pipeline de limpieza de la Fase 1.
    """
    st.header("Auditoría de calidad")
    st.markdown(
        "Los tres sistemas fuente de TechLogistics llegan con defectos que "
        "invalidarían cualquier conclusión de negocio si se usaran tal cual. "
        "Esta pestaña cuantifica el daño **antes** de tocar un solo dato."
    )

    st.markdown("#### Health Score de los datos crudos")
    _tarjetas_score(resultado, "antes")
    st.divider()

    _seccion_perfil_calidad(resultado)
    st.divider()

    _seccion_excluidos(resultado)
