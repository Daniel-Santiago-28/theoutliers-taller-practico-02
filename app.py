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
from ui.tabs import (auditoria, cliente, ficha_tecnica, insights_ia,
                     operaciones, transparencia, vision_general)

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
    # La política de curaduría se lee del estado del panel lateral antes de
    # dibujarlo: el panel necesita la SSOT para poblar sus opciones, y la SSOT
    # necesita la política. Streamlit aplica el estado de los widgets antes de
    # ejecutar el script, así que en la pasada siguiente a un cambio el valor
    # ya está disponible aquí y no hace falta forzar un rerun.
    politica = sidebar.politica_actual()

    try:
        integrado = cargar_ssot(politica)
    except ingest.ErrorIngesta as exc:
        st.error(f"No fue posible cargar los datos fuente.\n\n**{exc}**")
        st.stop()
    except integration.ErrorIntegracion as exc:
        st.error(f"Falló la integración de los activos.\n\n**{exc}**")
        st.stop()
    except (ValueError, KeyError, TypeError) as exc:
        st.error(f"Falló el proceso de curaduría.\n\n**{exc}**")
        st.stop()

    seleccion, _ = sidebar.construir(integrado.ssot)

    curaduria = cargar_curaduria(politica)
    recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
    ingreso_total = float(integrado.ssot["Ingreso_Bruto"].sum())

    sidebar.mostrar_alcance(recorte, len(integrado.ssot),
                            curaduria.reporte_csv())

    st.title("Sistema de Soporte a la Decisión")
    if seleccion.hay_filtro_activo:
        st.info(
            f"**Filtro activo** · {seleccion.describir()} "
            f"Las pestañas de Visión General, Operaciones, Cliente e "
            f"Insights de IA analizan únicamente estas {len(recorte):,} "
            f"transacciones.", icon="🔎")
    else:
        st.caption(
            f"Analizando la operación completa: {len(integrado.ssot):,} "
            f"transacciones. Use el panel lateral para acotar el análisis.")

    pestanas = st.tabs([
        "Visión General", "Auditoría", "Transparencia", "Operaciones",
        "Cliente", "Insights de IA", "Ficha Técnica",
    ])

    # Visión General recibe el recorte filtrado: es la puerta de entrada del
    # dashboard y debe reflejar tanto los filtros como el interruptor
    # "Incluir venta sin catálogo".
    with pestanas[0]:
        vision_general.renderizar(recorte, seleccion.describir())

    # Auditoría y Transparencia describen la curaduría de los archivos fuente,
    # que se ejecutó una sola vez sobre los tres activos completos. Recortarlas
    # con el filtro del usuario produciría un Health Score "de las Laptops
    # vendidas por Online", una cifra con apariencia de autoridad y sin
    # significado: la limpieza no se hizo por subconjunto. Reciben la curaduría
    # completa a propósito, y así lo declaran en pantalla.
    with pestanas[1]:
        auditoria.renderizar(curaduria)
    with pestanas[2]:
        transparencia.renderizar(curaduria, integrado)

    # Las tres pestañas de negocio reciben el recorte filtrado.
    with pestanas[3]:
        operaciones.renderizar(recorte, seleccion.describir(),
                               integrado.diagnostico_fantasma)
    with pestanas[4]:
        cliente.renderizar(recorte, seleccion.describir())
    with pestanas[5]:
        insights_ia.renderizar(
            recorte, seleccion.describir(), ingreso_total=ingreso_total,
            diagnostico_fantasma=integrado.diagnostico_fantasma)

    # Ficha Técnica es material de referencia, como Auditoría y Transparencia:
    # ignora el recorte a propósito. Sus ejemplos se calculan sobre la
    # operación completa para que sean estables y siempre reproducibles.
    with pestanas[6]:
        ficha_tecnica.renderizar(curaduria, integrado)


if __name__ == "__main__":
    main()
