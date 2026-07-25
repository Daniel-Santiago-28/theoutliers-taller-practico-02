"""Dashboard DSS de TechLogistics S.A.S.

Punto de entrada de la aplicación Streamlit. Este archivo solo orquesta: la
carga y el cálculo viven en ``src``, la presentación de cada pestaña en ``ui``.

Ejecución:
    streamlit run app.py
"""

from __future__ import annotations

import logging

import streamlit as st

from src import cleaning, filters, ingest, integration
from ui import sidebar
from ui.tabs import auditoria, cliente, operaciones, transparencia

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
def cargar_curaduria(politica_duplicados: str):
    """Ejecuta la limpieza de la Fase 1, cacheada entre interacciones."""
    return cleaning.ejecutar_pipeline(politica_duplicados=politica_duplicados)


@st.cache_data(show_spinner="Integrando la Sola Fuente de Verdad…")
def cargar_ssot(politica_duplicados: str):
    """Construye la SSOT de la Fase 2 sobre los datos ya curados."""
    curaduria = cargar_curaduria(politica_duplicados)
    return integration.construir_ssot(curaduria.limpios, curaduria.crudos)


def main() -> None:
    """Punto de entrada de la aplicación."""
    # La curaduría se ejecuta con la política por defecto para poder poblar
    # los controles del panel lateral; si el usuario la cambia, Streamlit
    # vuelve a ejecutar el script y el caché devuelve la variante elegida.
    politica_inicial = st.session_state.get("politica_duplicados", "conservar")

    try:
        integrado = cargar_ssot(politica_inicial)
    except ingest.ErrorIngesta as exc:
        st.error(f"No fue posible cargar los datos fuente.\n\n**{exc}**")
        st.stop()
    except integration.ErrorIntegracion as exc:
        st.error(f"Falló la integración de los activos.\n\n**{exc}**")
        st.stop()
    except (ValueError, KeyError, TypeError) as exc:
        st.error(f"Falló el proceso de curaduría.\n\n**{exc}**")
        st.stop()

    seleccion, politica = sidebar.construir(integrado.ssot)

    if politica != politica_inicial:
        st.session_state["politica_duplicados"] = politica
        st.rerun()

    curaduria = cargar_curaduria(politica)
    recorte = filters.aplicar_filtros(integrado.ssot, seleccion)

    pestanas = st.tabs([
        "Auditoría", "Transparencia", "Operaciones", "Cliente",
        "Insights de IA",
    ])

    with pestanas[0]:
        auditoria.renderizar(curaduria)
    with pestanas[1]:
        transparencia.renderizar(curaduria)
    with pestanas[2]:
        operaciones.renderizar(recorte, seleccion.describir(),
                               integrado.diagnostico_fantasma)
    with pestanas[3]:
        cliente.renderizar(recorte, seleccion.describir())
    with pestanas[4]:
        st.info("Disponible en la Fase 4: recomendaciones estratégicas "
                "generadas con Groq / Llama-3.", icon="🚧")


if __name__ == "__main__":
    main()
