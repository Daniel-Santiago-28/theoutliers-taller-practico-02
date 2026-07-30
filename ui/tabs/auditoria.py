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
            use_container_width=True, key="g_auditoria_nulidad")

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


# Qué implicó realmente cada exclusión. "Excluido" significa apartado de un
# cálculo concreto, nunca eliminado del dataset: la fila sigue presente con su
# bandera y con el resto de sus campos intactos.
_EFECTO_EXCLUSION = {
    "inventario_stock_negativo": (
        "Se truncó `Stock_Actual` a 0 y se marcó `Stock_Negativo_Corregido`. "
        "El SKU permanece en el maestro con todos sus demás campos."),
    "inventario_costo_atipico": (
        "Se anuló `Costo_Unitario_USD` y se marcó `Costo_Atipico_Excluido`. "
        "El SKU sigue en el maestro; solo queda fuera del cálculo de margen."),
    "transacciones_fecha_futura": (
        "Se marcó `Fecha_Futura`. La venta conserva su importe y cuenta en el "
        "ingreso total; solo se omite en las series de tiempo."),
    "transacciones_cantidad_invalida": (
        "Se anuló `Cantidad_Vendida` y se marcó `Cantidad_Invalida`. La "
        "transacción conserva su `Precio_Venta_Final`."),
    "transacciones_entrega_999": (
        "Se anuló el código de error y se imputó el tiempo de entrega; se "
        "marcó `Entrega_Codigo_Error`. La transacción queda intacta."),
    "feedback_rating_producto_fuera_escala": (
        "Se anuló `Rating_Producto`. La opinión conserva su rating logístico, "
        "su NPS y su comentario."),
    "feedback_id_colisionado_eliminado": (
        "⚠️ **Única exclusión que sí elimina filas.** Solo ocurre con la "
        "política 'Eliminar repeticiones' del panel lateral."),
}


def _seccion_excluidos(resultado: ResultadoLimpieza) -> None:
    """Visor de registros apartados de algún cálculo.

    La guía de validación exige una opción de "ver registros excluidos". El
    término se conserva por trazabilidad con el enunciado, pero se explicita
    que exclusión no es eliminación: salvo la política opcional de duplicados,
    ninguna fila se borra.
    """
    st.subheader("Registros excluidos de un cálculo")

    filas_antes = sum(len(f) for f in resultado.crudos.values())
    filas_despues = sum(len(f) for f in resultado.limpios.values())
    marcados = sum(len(f) for f in resultado.registro.excluidos.values())

    col1, col2, col3 = st.columns(3)
    col1.metric("Filas en los archivos originales", f"{filas_antes:,}")
    col2.metric("Filas tras la curaduría", f"{filas_despues:,}",
                delta=f"{filas_despues - filas_antes:,}",
                delta_color="off" if filas_antes == filas_despues else "normal")
    col3.metric("Registros apartados de algún cálculo", f"{marcados:,}")

    if filas_antes == filas_despues:
        st.success(
            "**Excluido no significa eliminado.** No se borró una sola fila. "
            "Cada registro listado abajo sigue presente en el dataset con "
            "todos sus demás campos; lo único que ocurre es que el valor "
            "corrupto se anuló y la fila quedó marcada con una bandera, de "
            "modo que un KPI puntual pueda omitirla sin que el ingreso total "
            "deje de ser trazable hasta el archivo original.", icon="✅")
    else:
        st.warning(
            f"La política de duplicados activa eliminó "
            f"{filas_antes - filas_despues:,} filas. Con la política "
            f"'Conservar y reparar la llave' no se pierde ningún registro.",
            icon="⚠️")

    excluidos = resultado.registro.excluidos
    if not excluidos:
        st.info("No se apartó ningún registro.")
        return

    etiquetas = {
        clave: f"{clave.replace('_', ' ').capitalize()} ({len(frame):,})"
        for clave, frame in excluidos.items()
    }
    seleccion = st.selectbox(
        "Motivo", list(excluidos),
        format_func=lambda c: etiquetas[c], key="auditoria_excluidos")

    efecto = _EFECTO_EXCLUSION.get(seleccion)
    if efecto:
        st.markdown(f"**Qué se hizo con estas filas:** {efecto}")

    frame = excluidos[seleccion]
    st.caption(
        "Se muestra el registro tal como venía en el archivo original, para "
        "que pueda compararse contra el valor curado.")
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.download_button(
        f"Descargar estos {len(frame):,} registros",
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
    st.caption(
        "**Alcance:** esta pestaña ignora los filtros del panel lateral a "
        "propósito. La curaduría se ejecutó una sola vez sobre los archivos "
        "fuente completos, así que un Health Score de un subconjunto no "
        "existiría como magnitud: la limpieza no se hizo por recorte. Los "
        "filtros sí actúan sobre Operaciones, Cliente e Insights de IA.")

    st.markdown("#### Health Score de los datos crudos")
    _tarjetas_score(resultado, "antes")
    st.divider()

    _seccion_perfil_calidad(resultado)
    st.divider()

    _seccion_excluidos(resultado)
