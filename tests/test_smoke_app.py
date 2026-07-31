"""Pruebas de humo de la aplicación completa con AppTest de Streamlit.

Estas pruebas ejecutan `app.py` de verdad, sin navegador, y verifican que
ningún recorte de filtros produzca una excepción. Cubren la clase de fallo que
los tests unitarios no ven: los que solo ocurren al *renderizar*.

Justifican su costo con dos defectos reales que atraparon:

1. ``StreamlitDuplicateElementId``. Con un rango de fechas estrecho ningún
   grupo alcanzaba el mínimo de 30 filas, así que dos gráficas devolvían la
   misma figura vacía. Streamlit deriva el identificador del elemento de su
   contenido, y dos figuras idénticas colisionaban. Se corrigió pasando una
   clave explícita a las 17 llamadas a ``plotly_chart``.
2. ``TypeError`` al formatear un tamaño de efecto nulo. Con muestras pequeñas
   el veredicto no tiene coeficiente, y el diagnóstico de la pregunta 5 lo
   interpolaba como número.

Ambos aparecían solo con filtros estrechos, que es exactamente lo primero que
prueba cualquier evaluador.
"""

from datetime import date

import pytest

pytest.importorskip("streamlit.testing.v1",
                    reason="Requiere el arnés de pruebas de Streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

# La primera ejecución paga la limpieza y la integración completas; las
# siguientes reutilizan el caché del proceso.
TIEMPO_LIMITE = 240


def _app() -> AppTest:
    """Arranca la aplicación y verifica que el estado inicial sea sano."""
    at = AppTest.from_file("app.py", default_timeout=TIEMPO_LIMITE)
    at.run()
    assert not at.exception, f"La app falló al arrancar: {at.exception}"
    return at


def _sin_excepcion(at: AppTest, contexto: str) -> None:
    if at.exception:
        pytest.fail(f"Excepción con {contexto}: "
                    f"{at.exception[0].message}")


@pytest.mark.smoke
class TestArranque:
    """El estado por defecto debe renderizar sin errores."""

    def test_arranca_limpio(self):
        at = _app()
        assert at.tabs, "No se renderizaron las pestañas"

    def test_expone_los_controles_esperados(self):
        at = _app()
        assert len(at.date_input) == 1, "Falta el selector de rango de fechas"
        assert len(at.multiselect) == 4, (
            "Faltan categoría, bodega, ciudad o canal")
        assert len(at.toggle) >= 1, "Falta el interruptor de venta fantasma"

    def test_hay_cinco_pestanas(self):
        at = _app()
        assert len(at.tabs) == 5


@pytest.mark.smoke
class TestRangosDeFechaEstrechos:
    """El defecto original: pocos días dejaban grupos bajo el mínimo."""

    @pytest.mark.parametrize("desde,hasta,etiqueta", [
        (date(2024, 9, 24), date(2024, 9, 24), "un solo día"),
        (date(2024, 9, 24), date(2024, 9, 25), "dos días"),
        (date(2025, 3, 1), date(2025, 3, 7), "una semana"),
        (date(2025, 6, 1), date(2025, 6, 30), "un mes"),
    ])
    def test_rango_estrecho_no_revienta(self, desde, hasta, etiqueta):
        at = _app()
        at.date_input[0].set_value((desde, hasta)).run()
        _sin_excepcion(at, f"rango de {etiqueta}")

    def test_rango_completo_sigue_funcionando(self):
        at = _app()
        at.date_input[0].set_value((date(2024, 9, 23), date(2026, 2, 4))).run()
        _sin_excepcion(at, "el rango completo")


@pytest.mark.smoke
class TestFiltrosCategoricos:
    """Cada filtro por separado y en combinación."""

    def test_una_sola_categoria(self):
        at = _app()
        at.multiselect[0].set_value(["Laptops"]).run()
        _sin_excepcion(at, "la categoría Laptops")

    def test_solo_venta_sin_catalogo(self):
        """Recorte sin costo conocido: el margen no es calculable."""
        at = _app()
        at.multiselect[0].set_value(["Sin_Catalogo_Oficial"]).run()
        _sin_excepcion(at, "solo la venta sin catálogo")

    def test_una_sola_bodega(self):
        at = _app()
        at.multiselect[1].set_value(["Norte"]).run()
        _sin_excepcion(at, "la bodega Norte")

    def test_una_bodega_sin_nomenclatura_estandar(self):
        at = _app()
        at.multiselect[1].set_value(["Zona_Franca"]).run()
        _sin_excepcion(at, "la bodega Zona_Franca")

    def test_una_sola_ciudad(self):
        at = _app()
        at.multiselect[2].set_value(["Medellín"]).run()
        _sin_excepcion(at, "la ciudad Medellín")

    def test_un_solo_canal(self):
        at = _app()
        at.multiselect[3].set_value(["Online"]).run()
        _sin_excepcion(at, "el canal Online")

    def test_excluir_la_venta_fantasma(self):
        at = _app()
        at.toggle[0].set_value(False).run()
        _sin_excepcion(at, "la venta fantasma excluida")


@pytest.mark.smoke
class TestRecortesExtremos:
    """Combinaciones que dejan el recorte casi o completamente vacío."""

    def test_tres_filtros_mas_una_semana(self):
        at = _app()
        at.multiselect[0].set_value(["Laptops"]).run()
        at.multiselect[1].set_value(["Norte"]).run()
        at.multiselect[3].set_value(["Online"]).run()
        at.date_input[0].set_value((date(2025, 3, 1), date(2025, 3, 7))).run()
        _sin_excepcion(at, "tres filtros y una semana")

    def test_recorte_practicamente_imposible(self):
        at = _app()
        at.multiselect[0].set_value(["Tablets"]).run()
        at.multiselect[1].set_value(["Zona_Franca"]).run()
        at.date_input[0].set_value((date(2024, 9, 24), date(2024, 9, 24))).run()
        _sin_excepcion(at, "un recorte prácticamente vacío")

    def test_el_filtro_realmente_cambia_la_pantalla(self):
        """Si el contenido no cambia, los filtros no están propagando."""
        at = _app()
        antes = [m.value for m in at.metric]

        at.multiselect[0].set_value(["Laptops"]).run()
        _sin_excepcion(at, "el filtro de categoría")
        despues = [m.value for m in at.metric]

        assert antes != despues, (
            "Los indicadores no cambiaron al filtrar: el recorte no propaga")


@pytest.mark.smoke
class TestPoliticaDeDuplicados:
    """El control de curaduría reconstruye todo el pipeline."""

    def test_cambiar_a_eliminar_no_revienta(self):
        at = _app()
        at.radio[0].set_value("eliminar").run()
        _sin_excepcion(at, "la política de eliminar duplicados")


@pytest.mark.smoke
class TestReiniciarFiltros:
    """El botón debe devolver los seis controles a su estado inicial.

    Los botones se localizan por clave y no por posición: ``at.button``
    recorre el contenedor principal antes que la barra lateral, así que el
    índice 0 es el botón de la pestaña de IA y no el del panel.
    """

    CLAVE = "boton_reiniciar_filtros"

    def _aplicar_los_seis_filtros(self, at) -> None:
        at.multiselect[0].set_value(["Laptops"]).run()
        at.multiselect[1].set_value(["Norte"]).run()
        at.multiselect[2].set_value(["Medellín"]).run()
        at.multiselect[3].set_value(["Online"]).run()
        at.toggle[0].set_value(False).run()
        at.date_input[0].set_value((date(2025, 3, 1), date(2025, 3, 7))).run()

    def test_deshabilitado_cuando_no_hay_nada_que_reiniciar(self):
        at = _app()
        assert at.button(key=self.CLAVE).disabled, (
            "Sin filtros activos el botón no debe poder pulsarse")

    def test_se_habilita_al_aplicar_un_filtro(self):
        at = _app()
        at.multiselect[0].set_value(["Laptops"]).run()
        assert not at.button(key=self.CLAVE).disabled

    def test_se_habilita_solo_por_cambiar_la_fecha(self):
        """El rango de fechas también cuenta como filtro activo."""
        at = _app()
        at.date_input[0].set_value((date(2025, 1, 1), date(2025, 6, 30))).run()
        assert not at.button(key=self.CLAVE).disabled

    def test_reinicia_los_seis_controles(self):
        at = _app()
        fecha_inicial = at.date_input[0].value

        self._aplicar_los_seis_filtros(at)
        assert at.multiselect[0].value == ["Laptops"]
        assert at.date_input[0].value != fecha_inicial

        at.button(key=self.CLAVE).click().run()
        _sin_excepcion(at, "el reinicio de filtros")

        assert at.multiselect[0].value == []
        assert at.multiselect[1].value == []
        assert at.multiselect[2].value == []
        assert at.multiselect[3].value == []
        assert at.toggle[0].value is True
        assert at.date_input[0].value == fecha_inicial, (
            "La fecha debe volver al rango completo original")

    def test_tras_reiniciar_vuelve_a_deshabilitarse(self):
        at = _app()
        self._aplicar_los_seis_filtros(at)
        at.button(key=self.CLAVE).click().run()
        assert at.button(key=self.CLAVE).disabled

    def test_no_altera_la_politica_de_curaduria(self):
        """Reiniciar filtros no debe tocar una decisión de curaduría."""
        at = _app()
        at.radio[0].set_value("eliminar").run()
        at.multiselect[0].set_value(["Laptops"]).run()

        at.button(key=self.CLAVE).click().run()
        _sin_excepcion(at, "el reinicio con política alterada")

        assert at.multiselect[0].value == []
        assert at.radio[0].value == "eliminar", (
            "La política de duplicados no es un filtro y debe conservarse")
