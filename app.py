"""Dashboard DSS de TechLogistics S.A.S.

Punto de entrada de la aplicación Streamlit. Este archivo solo orquesta: la
carga y el cálculo viven en ``src``, la presentación de cada pestaña en ``ui``.

Ejecución:
    streamlit run app.py
"""

from __future__ import annotations

import logging

import streamlit as st

from src import cleaning, config, ingest
from ui.tabs import auditoria, transparencia

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(
    page_title="DSS · TechLogistics S.A.S.",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner="Auditando y curando los datos…")
def cargar_resultado(politica_duplicados: str):
    """Ejecuta el pipeline completo, cacheado entre interacciones.

    Args:
        politica_duplicados: Política aplicada a la colisión de Feedback_ID.

    Returns:
        ResultadoLimpieza con crudos, limpios, bitácora y Health Scores.
    """
    return cleaning.ejecutar_pipeline(politica_duplicados=politica_duplicados)


def construir_sidebar() -> dict:
    """Dibuja la barra lateral y devuelve la configuración elegida."""
    with st.sidebar:
        st.title("TechLogistics S.A.S.")
        st.caption("Sistema de Soporte a la Decisión")

        st.markdown("### Curaduría")
        politica = st.radio(
            "Colisión de `Feedback_ID`",
            options=["conservar", "eliminar"],
            format_func=lambda v: {
                "conservar": "Conservar y reparar la llave",
                "eliminar": "Eliminar repeticiones",
            }[v],
            help=(
                "El activo de feedback no contiene duplicados reales: los "
                "identificadores repetidos apuntan a transacciones distintas, "
                "con clientes y calificaciones distintos. Conservar repara la "
                "llave sin perder opiniones; eliminar aplica la lectura "
                "literal del enunciado y descarta 500 registros legítimos."),
        )

        st.divider()
        refrescar = st.button("Refrescar análisis", use_container_width=True,
                              type="primary")
        if refrescar:
            st.cache_data.clear()

        st.divider()
        st.caption(
            f"Validación temporal contra la fecha del sistema: "
            f"**{config.fecha_corte()}**  \n"
            "Los filtros de fecha, categoría y bodega se habilitan en la "
            "Fase 3, junto con las pestañas de negocio.")

    return {"politica_duplicados": politica}


def main() -> None:
    """Punto de entrada de la aplicación."""
    opciones = construir_sidebar()

    try:
        resultado = cargar_resultado(opciones["politica_duplicados"])
    except ingest.ErrorIngesta as exc:
        st.error(f"No fue posible cargar los datos fuente.\n\n**{exc}**")
        st.stop()
    except (ValueError, KeyError, TypeError) as exc:
        st.error(f"Falló el proceso de curaduría.\n\n**{exc}**")
        st.stop()

    pestanas = st.tabs([
        "Auditoría", "Transparencia", "Operaciones", "Cliente",
        "Insights de IA",
    ])

    with pestanas[0]:
        auditoria.renderizar(resultado)
    with pestanas[1]:
        transparencia.renderizar(resultado)
    with pestanas[2]:
        st.info("Disponible en la Fase 3: rentabilidad, venta fantasma y "
                "cuellos de botella logísticos.", icon="🚧")
    with pestanas[3]:
        st.info("Disponible en la Fase 3: paradoja de fidelidad y riesgo "
                "operativo por bodega.", icon="🚧")
    with pestanas[4]:
        st.info("Disponible en la Fase 4: recomendaciones estratégicas "
                "generadas con Groq / Llama-3.", icon="🚧")


if __name__ == "__main__":
    main()
