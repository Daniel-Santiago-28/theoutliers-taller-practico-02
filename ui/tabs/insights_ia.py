"""Pestaña de Insights de IA: recomendación estratégica con Groq (Llama-3).

El análisis se dispara con un botón explícito y se calcula sobre el recorte
que el usuario tiene aplicado en el panel lateral, no sobre el dataset
completo. El resultado se guarda en la sesión para que cambiar de pestaña no
obligue a volver a pagar la llamada al modelo.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src import ai_insights, config

_CLAVE_SESION = "resultado_ia"
_CLAVE_FILTRO = "filtro_del_analisis_ia"


def _mostrar_error(error: ai_insights.ErrorIA) -> None:
    """Presenta un fallo del servicio sin tumbar la aplicación."""
    st.error(f"**{error.mensaje}**", icon="🚫")
    if error.sugerencia:
        st.info(error.sugerencia, icon="💡")


def _panel_configuracion() -> bool:
    """Verifica que haya clave disponible y explica cómo cargarla si no.

    Returns:
        True si el análisis puede ejecutarse.
    """
    try:
        ai_insights.obtener_clave()
        return True
    except ai_insights.ClaveNoConfigurada as error:
        st.warning(f"**{error.mensaje}** {error.sugerencia}", icon="🔑")
        with st.expander("Cómo configurar la clave"):
            st.markdown(
                "La clave **nunca** se escribe en el código ni se sube al "
                "repositorio. Elija una de las dos vías:")
            st.code(
                "# Opción A — ejecución local\n"
                "cp .env.example .env\n"
                "# edite .env y ponga su clave en GROQ_API_KEY\n\n"
                "# Opción B — secretos de Streamlit\n"
                "cp .streamlit/secrets.toml.example .streamlit/secrets.toml",
                language="bash")
            st.markdown(
                "En Streamlit Community Cloud, cárguela en "
                "*Settings → Secrets*. Puede obtener una gratuita en "
                "[console.groq.com/keys](https://console.groq.com/keys).")
        return False


def _mostrar_resultado(resultado: ai_insights.ResultadoIA,
                       filtro_original: str) -> None:
    """Presenta los tres párrafos y la traza de lo que se envió al modelo."""
    if filtro_original != st.session_state.get(_CLAVE_FILTRO):
        st.warning(
            "Los filtros cambiaron después de generar este análisis. Vuelva a "
            "ejecutarlo para que corresponda al recorte actual.", icon="⚠️")

    st.markdown("#### Recomendación estratégica")
    st.caption(f"Generado por `{resultado.modelo}` sobre el recorte: "
               f"{filtro_original}")

    for indice, parrafo in enumerate(resultado.parrafos, start=1):
        with st.container(border=True):
            st.markdown(f"**{indice}.** {parrafo}")

    if len(resultado.parrafos) != 3:
        st.caption(
            f"⚠️ El modelo devolvió {len(resultado.parrafos)} párrafos en lugar "
            f"de tres. El texto se muestra tal como llegó, sin recortarlo.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Tokens de entrada", f"{resultado.tokens_entrada:,}")
    col2.metric("Tokens de salida", f"{resultado.tokens_salida:,}")
    col3.metric("Temperatura", f"{config.TEMPERATURA_GROQ}",
                help="Baja a propósito: se busca análisis reproducible")

    st.download_button(
        "Descargar la recomendación",
        data=resultado.texto.encode("utf-8-sig"),
        file_name="recomendacion_estrategica_ia.txt", mime="text/plain",
        key="descarga_ia")

    with st.expander("Auditar exactamente qué recibió el modelo"):
        st.caption(
            "El modelo no ve el dataset: ve este resumen ya calculado. Toda "
            "cifra que aparezca en la recomendación tiene que estar aquí, y "
            "cada hallazgo viaja con su veredicto de solidez para que el "
            "modelo no pueda recomendar actuar sobre ruido.")
        st.text(resultado.prompt_usuario)
        st.download_button(
            "Descargar el resumen enviado (JSON)",
            data=json.dumps(resultado.resumen_enviado, ensure_ascii=False,
                            indent=2).encode("utf-8"),
            file_name="resumen_enviado_a_ia.json", mime="application/json",
            key="descarga_resumen_ia")

    with st.expander("Ver el prompt de sistema"):
        st.text(ai_insights.PROMPT_SISTEMA)


def renderizar(recorte: pd.DataFrame, descripcion_filtro: str,
               ingreso_total: float | None = None,
               diagnostico_fantasma: dict | None = None) -> None:
    """Dibuja la pestaña de Insights de IA.

    Args:
        recorte: SSOT ya filtrada por la selección del usuario.
        descripcion_filtro: Texto legible del recorte aplicado.
        ingreso_total: Ingreso de la operación sin filtrar, como referencia.
        diagnostico_fantasma: Diagnóstico de seis criterios de la Fase 2.
    """
    st.header("Insights de IA")
    st.markdown(
        "Un modelo Llama-3 alojado en Groq redacta tres párrafos de "
        "recomendación estratégica **sobre el recorte que usted tiene "
        "aplicado**, no sobre la operación completa.")
    st.caption(descripcion_filtro)

    if recorte.empty:
        st.warning(
            "El filtro aplicado no deja transacciones que analizar. Amplíe el "
            "rango de fechas o quite alguna restricción del panel lateral.",
            icon="⚠️")
        return

    hay_clave = _panel_configuracion()

    col_boton, col_info = st.columns([1, 3])
    with col_boton:
        disparar = st.button(
            "Generar análisis con IA", type="primary",
            use_container_width=True, disabled=not hay_clave)
    with col_info:
        st.caption(
            f"Se enviarán únicamente las cifras agregadas de "
            f"{len(recorte):,} transacciones. Ningún dato individual de "
            f"cliente o transacción sale de la aplicación.")

    if disparar:
        try:
            with st.spinner("Consultando a Llama-3…"):
                resumen = ai_insights.construir_resumen(
                    recorte, descripcion_filtro, ingreso_total,
                    diagnostico_fantasma)
                resultado = ai_insights.generar_recomendaciones(resumen)
            st.session_state[_CLAVE_SESION] = resultado
            st.session_state[_CLAVE_FILTRO] = descripcion_filtro
        except ValueError as error:
            st.warning(str(error), icon="⚠️")
            return
        except ai_insights.ErrorIA as error:
            _mostrar_error(error)
            return

    guardado = st.session_state.get(_CLAVE_SESION)
    if guardado is not None:
        st.divider()
        _mostrar_resultado(
            guardado, st.session_state.get(_CLAVE_FILTRO, descripcion_filtro))
    elif hay_clave:
        st.info(
            "Aplique los filtros que le interesen en el panel lateral y pulse "
            "**Generar análisis con IA**.", icon="👈")
