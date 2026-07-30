"""Barra lateral: filtros del análisis y controles de curaduría.

Solo dibuja controles y devuelve la selección. La lógica de recorte vive en
``src.filters``, de modo que el mismo filtro que ve el usuario pueda
reproducirse en un test o alimentar el prompt del módulo de IA.
"""

from __future__ import annotations

import streamlit as st

from src import config
from src.filters import Filtros, opciones_disponibles

# Claves de estado de los controles de filtrado. Se declaran explícitamente
# porque son la única vía para poder reiniciarlos: sin una clave, Streamlit no
# expone el estado del widget y no hay forma de devolverlo a su valor inicial.
CLAVES_FILTRO = (
    "filtro_fechas", "filtro_categorias", "filtro_bodegas", "filtro_canales",
    "filtro_incluir_fantasma",
)

# La política de duplicados NO está en CLAVES_FILTRO a propósito: es una
# decisión de curaduría que reconstruye el pipeline completo, no un filtro de
# análisis, y reiniciarla junto con los filtros sería una sorpresa.
CLAVE_POLITICA = "politica_duplicados"
POLITICA_POR_DEFECTO = "conservar"


def politica_actual() -> str:
    """Política de duplicados vigente, legible antes de dibujar el panel.

    ``app.py`` necesita este valor al inicio del script para cargar la Sola
    Fuente de Verdad, pero el control que lo define vive en la barra lateral,
    que a su vez necesita la SSOT para poblar sus opciones. Leer el estado del
    widget rompe esa circularidad sin recurrir a un rerun manual.
    """
    return st.session_state.get(CLAVE_POLITICA, POLITICA_POR_DEFECTO)


def _reiniciar_filtros() -> None:
    """Devuelve todos los controles de filtrado a su estado inicial.

    Se borran las entradas de ``session_state`` en lugar de reasignarles el
    valor por defecto: al recrearse sin estado previo, cada widget vuelve a
    tomar el ``value`` que declara su definición. Así el valor por defecto se
    define en un solo sitio y no hay riesgo de que las dos copias divergan.

    No toca la política de duplicados: esa es una decisión de curaduría, no un
    filtro de análisis, y reiniciarla sin avisar sería una sorpresa.
    """
    for clave in CLAVES_FILTRO:
        st.session_state.pop(clave, None)


def construir(ssot) -> tuple[Filtros, str]:
    """Dibuja la barra lateral completa.

    Args:
        ssot: Sola Fuente de Verdad, para poblar las opciones disponibles.

    Returns:
        Tupla (filtros seleccionados, política de duplicados elegida).
    """
    opciones = opciones_disponibles(ssot)

    with st.sidebar:
        st.title("TechLogistics S.A.S.")
        st.caption("Sistema de Soporte a la Decisión")

        st.markdown("### Filtros del análisis")

        rango = st.date_input(
            "Rango de fechas de venta",
            value=(opciones["fecha_min"], opciones["fecha_max"]),
            min_value=opciones["fecha_min"], max_value=opciones["fecha_max"],
            key="filtro_fechas",
            help="Acota el periodo. Todas las pestañas se recalculan.")
        # date_input devuelve una tupla incompleta mientras el usuario elige
        # la segunda fecha; hay que tolerarlo o la app revienta a mitad de clic.
        desde, hasta = (rango if isinstance(rango, tuple) and len(rango) == 2
                        else (opciones["fecha_min"], opciones["fecha_max"]))

        categorias = st.multiselect(
            "Categoría", options=opciones["categorias"],
            key="filtro_categorias",
            help="Vacío = todas. 'Sin_Catalogo_Oficial' son las ventas cuyo "
                 "SKU no existe en el maestro de inventario.")

        bodegas = st.multiselect(
            "Bodega de origen", options=opciones["bodegas"],
            key="filtro_bodegas", help="Vacío = todas.")

        canales = st.multiselect(
            "Canal de venta", options=opciones["canales"],
            key="filtro_canales",
            help="Vacío = todos. Permite aislar el canal Online que la junta "
                 "señala en la pregunta de rentabilidad.")

        incluir_fantasma = st.toggle(
            "Incluir venta sin catálogo", value=True,
            key="filtro_incluir_fantasma",
            help="Las ventas cuyo SKU no está en el maestro no tienen costo "
                 "conocido, así que no aportan margen. Se incluyen por "
                 "defecto para que el ingreso total siga siendo trazable.")

        # Un filtro está activo si algún control se movió de su valor inicial.
        # Se evalúa aquí, con los valores ya leídos, para poder deshabilitar el
        # reinicio cuando no hay nada que reiniciar.
        hay_filtro = bool(
            categorias or bodegas or canales or not incluir_fantasma
            or desde != opciones["fecha_min"]
            or hasta != opciones["fecha_max"])

        st.divider()

        # Ambos botones actúan por callback y no con el patrón
        # `if st.button(...): ...; st.rerun()`. El motivo es concreto: estos
        # controles se dibujan antes que el radio de curaduría, y un
        # `st.rerun()` aborta el script en este punto. El radio nunca llegaría
        # a registrarse en esa pasada y Streamlit descartaría su estado por
        # considerarlo un widget huérfano, revirtiendo la política elegida. Un
        # callback se ejecuta antes de reejecutar el script, que luego corre
        # completo.
        st.button("Reiniciar filtros", use_container_width=True,
                  disabled=not hay_filtro, key="boton_reiniciar_filtros",
                  on_click=_reiniciar_filtros,
                  help="Devuelve fecha, categoría, bodega, canal y venta sin "
                       "catálogo a su estado inicial. No altera las opciones "
                       "de curaduría.")

        st.button("Refrescar análisis", use_container_width=True,
                  type="primary", key="boton_refrescar_analisis",
                  on_click=st.cache_data.clear,
                  help="Vacía el caché y recalcula la curaduría, la "
                       "integración y los análisis desde los archivos "
                       "fuente. Conserva los filtros aplicados.")

        with st.expander("Opciones de curaduría"):
            # La clave es la fuente de verdad de esta opción: ``app.py`` la lee
            # de session_state al inicio del script para poder cargar la SSOT
            # antes de dibujar el panel. Streamlit aplica el estado del widget
            # antes de ejecutar el script, así que en la pasada siguiente a un
            # cambio ya está el valor nuevo, sin necesidad de un rerun manual.
            politica = st.radio(
                "Colisión de `Feedback_ID`",
                options=["conservar", "eliminar"],
                key=CLAVE_POLITICA,
                format_func=lambda v: {
                    "conservar": "Conservar y reparar la llave",
                    "eliminar": "Eliminar repeticiones",
                }[v],
                help=(
                    "El activo de feedback no contiene duplicados reales: los "
                    "identificadores repetidos apuntan a transacciones "
                    "distintas, con clientes y calificaciones distintos. "
                    "Conservar repara la llave sin perder opiniones; eliminar "
                    "aplica la lectura literal del enunciado y descarta 500 "
                    "registros legítimos."))

        st.divider()
        st.caption(
            f"Validación temporal contra la fecha del sistema: "
            f"**{config.fecha_corte()}**")

    filtros = Filtros(
        fecha_desde=desde, fecha_hasta=hasta,
        categorias=tuple(categorias), bodegas=tuple(bodegas),
        canales=tuple(canales), incluir_fantasma=incluir_fantasma)

    return filtros, politica


def mostrar_alcance(recorte, total: int, reporte_csv: str) -> None:
    """Añade al panel lateral el alcance del recorte y la descarga del reporte.

    Se dibuja después de aplicar el filtro, no dentro de ``construir``, porque
    necesita el resultado del recorte. Streamlit permite escribir en la barra
    lateral desde cualquier punto del script.

    El contador de filas es la prueba más directa de que los filtros están
    vivos: si el usuario cambia una categoría y este número no se mueve, el
    filtrado está roto.

    Args:
        recorte: SSOT ya filtrada.
        total: Número de transacciones sin filtrar.
        reporte_csv: Bitácora de limpieza serializada, para descargar.
    """
    with st.sidebar:
        st.divider()
        st.markdown("### Alcance del análisis")

        filas = len(recorte)
        porcentaje = 100 * filas / total if total else 0.0
        st.metric("Transacciones analizadas", f"{filas:,}",
                  delta=f"{filas - total:,}" if filas != total else None,
                  delta_color="off",
                  help=f"{porcentaje:.1f} % de las {total:,} transacciones "
                       f"de la operación completa")

        if filas == 0:
            st.error(
                "El filtro no deja transacciones. Amplíe el rango de fechas o "
                "quite alguna restricción.", icon="⚠️")
        else:
            ingreso = float(recorte["Ingreso_Bruto"].sum())
            st.caption(f"Ingreso del recorte: **USD {ingreso:,.0f}**")

        st.divider()
        st.markdown("### Reporte de limpieza")
        st.download_button(
            "Descargar bitácora (CSV)",
            data=reporte_csv.encode("utf-8-sig"),
            file_name="reporte_limpieza_decisiones.csv", mime="text/csv",
            use_container_width=True, key="descarga_reporte_sidebar",
            help="Las 25 decisiones de curaduría con su justificación "
                 "estadística. Versión completa en la pestaña Transparencia.")
