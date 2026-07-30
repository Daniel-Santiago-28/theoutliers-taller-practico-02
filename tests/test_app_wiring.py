"""Pruebas del contrato de orquestación de la aplicación.

No verifican cómo se ve la interfaz, sino que el cableado entre capas sea
correcto: que el recorte del usuario llegue efectivamente a cada análisis y
que un filtro distinto produzca un resultado distinto.

Un dashboard con filtros que no propagan es peor que uno sin filtros: presenta
cifras globales bajo un encabezado que promete un subconjunto, y nadie lo nota
hasta que alguien decide sobre ellas.
"""

import pytest

from src import ai_insights, analytics, filters


# Recortes con los que se contrasta la propagación. Cada uno debe producir
# cifras distintas del total; si alguno coincide, el filtro no se aplicó.
RECORTES = {
    "una_categoria": filters.Filtros(categorias=("Laptops",)),
    "un_canal": filters.Filtros(canales=("Online",)),
    "una_bodega": filters.Filtros(bodegas=("Norte",)),
    "sin_fantasma": filters.Filtros(incluir_fantasma=False),
    "combinado": filters.Filtros(categorias=("Laptops",),
                                 canales=("Online",), bodegas=("Norte",)),
}


class TestPropagacionDelFiltro:
    """El recorte debe llegar a las tres capas de negocio."""

    @pytest.mark.parametrize("nombre", list(RECORTES))
    def test_el_filtro_reduce_el_recorte(self, integrado, nombre):
        recorte = filters.aplicar_filtros(integrado.ssot, RECORTES[nombre])
        assert 0 < len(recorte) < len(integrado.ssot)

    # 'sin_fantasma' se excluye a propósito: ver
    # test_excluir_fantasma_no_altera_el_analisis_de_margen.
    @pytest.mark.parametrize(
        "nombre", [n for n in RECORTES if n != "sin_fantasma"])
    def test_pregunta_1_responde_al_filtro(self, integrado, nombre):
        completo = analytics.analizar_fuga_capital(integrado.ssot)
        recorte = filters.aplicar_filtros(integrado.ssot, RECORTES[nombre])
        filtrado = analytics.analizar_fuga_capital(recorte)

        assert (filtrado.kpis["perdida_total_usd"]
                < completo.kpis["perdida_total_usd"])
        assert (filtrado.kpis["skus_analizados"]
                <= completo.kpis["skus_analizados"])

    def test_excluir_fantasma_no_altera_el_analisis_de_margen(self, integrado):
        """Propiedad de corrección, no un filtro que no propaga.

        La venta sin catálogo nunca entró en el análisis de rentabilidad: sin
        costo conocido su margen es nulo, y ``analizar_fuga_capital`` solo
        opera sobre las filas con margen calculable. Excluirla del recorte debe
        dejar la pérdida idéntica al centavo. Si esta prueba empezara a
        fallar, significaría que el margen de la venta fantasma se está
        computando como cero en algún punto, lo que inventaría rentabilidad
        donde no hay dato.
        """
        completo = analytics.analizar_fuga_capital(integrado.ssot)
        recorte = filters.aplicar_filtros(integrado.ssot,
                                          RECORTES["sin_fantasma"])
        filtrado = analytics.analizar_fuga_capital(recorte)

        assert (filtrado.kpis["perdida_total_usd"]
                == pytest.approx(completo.kpis["perdida_total_usd"]))
        assert (filtrado.kpis["skus_analizados"]
                == completo.kpis["skus_analizados"])
        # Sí debe desaparecer la advertencia sobre las filas sin costo.
        assert completo.advertencias and not filtrado.advertencias

    @pytest.mark.parametrize("nombre", ["una_categoria", "un_canal",
                                        "una_bodega"])
    def test_pregunta_2_responde_al_filtro(self, integrado, nombre):
        recorte = filters.aplicar_filtros(integrado.ssot, RECORTES[nombre])
        filtrado = analytics.analizar_crisis_logistica(recorte)
        assert filtrado.kpis["trx_con_estado"] < len(integrado.ssot)

    @pytest.mark.parametrize("nombre", list(RECORTES))
    def test_pregunta_3_responde_al_filtro(self, integrado, nombre):
        completo = analytics.analizar_venta_invisible(integrado.ssot)
        recorte = filters.aplicar_filtros(integrado.ssot, RECORTES[nombre])
        filtrado = analytics.analizar_venta_invisible(recorte)

        assert (filtrado.kpis["ingreso_usd"]
                <= completo.kpis["ingreso_usd"])
        assert (filtrado.kpis["transacciones"]
                <= completo.kpis["transacciones"])

    def test_filtrar_por_una_categoria_deja_una_sola(self, integrado):
        recorte = filters.aplicar_filtros(integrado.ssot,
                                          RECORTES["una_categoria"])
        q4 = analytics.analizar_paradoja_fidelidad(recorte)
        assert list(q4.por_categoria["Categoria_Analisis"]) == ["Laptops"]

    def test_filtrar_por_una_bodega_deja_una_sola(self, integrado):
        recorte = filters.aplicar_filtros(integrado.ssot,
                                          RECORTES["una_bodega"])
        q5 = analytics.analizar_riesgo_operativo(recorte)
        assert list(q5.por_bodega["Bodega_Origen"]) == ["Norte"]

    def test_excluir_fantasma_elimina_la_venta_invisible(self, integrado):
        """El interruptor del panel lateral debe anular la pregunta 3."""
        recorte = filters.aplicar_filtros(integrado.ssot,
                                          RECORTES["sin_fantasma"])
        q3 = analytics.analizar_venta_invisible(recorte)
        assert q3.kpis["ingreso_usd"] == 0
        assert q3.kpis["transacciones"] == 0


class TestPropagacionAlModuloDeIA:
    """Requisito de la guía: la IA analiza *exclusivamente* lo filtrado."""

    @pytest.mark.parametrize("nombre", list(RECORTES))
    def test_el_resumen_refleja_el_recorte(self, integrado, nombre):
        seleccion = RECORTES[nombre]
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        total = float(integrado.ssot["Ingreso_Bruto"].sum())

        resumen = ai_insights.construir_resumen(
            recorte, seleccion.describir(), total)

        assert resumen["transacciones"] == f"{len(recorte):,}"
        assert float(resumen["pct_ingreso"].replace(",", ".")) < 100.0

    def test_el_prompt_declara_el_recorte(self, integrado):
        """El modelo debe saber que analiza un subconjunto, no el total."""
        seleccion = RECORTES["combinado"]
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        resumen = ai_insights.construir_resumen(recorte, seleccion.describir())
        _, usuario = ai_insights.construir_prompt(resumen)

        assert "Laptops" in usuario
        assert "Online" in usuario
        assert "Norte" in usuario

    def test_dos_recortes_distintos_dan_prompts_distintos(self, integrado):
        """Si el prompt no cambia, la IA no está viendo el filtro."""
        prompts = set()
        for seleccion in (RECORTES["una_categoria"], RECORTES["un_canal"]):
            recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
            resumen = ai_insights.construir_resumen(recorte,
                                                    seleccion.describir())
            prompts.add(ai_insights.construir_prompt(resumen)[1])
        assert len(prompts) == 2

    def test_el_prompt_no_filtrado_declara_la_operacion_completa(
            self, integrado):
        sin_filtro = filters.Filtros()
        resumen = ai_insights.construir_resumen(
            integrado.ssot, sin_filtro.describir(),
            float(integrado.ssot["Ingreso_Bruto"].sum()))
        assert "operación completa" in resumen["recorte"]
        assert resumen["transacciones"] == "10,000"


class TestAlcanceDeLaCuraduria:
    """Auditoría y Transparencia describen los archivos fuente completos.

    No reciben el recorte a propósito: la limpieza se ejecutó una sola vez
    sobre los tres activos, así que un Health Score por subconjunto no existe
    como magnitud. Estas pruebas congelan esa decisión para que un cambio
    futuro que intente filtrarlas falle de forma visible.
    """

    def test_el_health_score_no_depende_del_filtro(self, pipeline_limpieza):
        """El score se mide sobre el esquema y las filas del archivo fuente."""
        for nombre, score in pipeline_limpieza.scores_antes.items():
            assert score.filas == len(pipeline_limpieza.crudos[nombre])

    def test_el_comparativo_cubre_los_tres_activos_completos(
            self, pipeline_limpieza):
        comparativo = pipeline_limpieza.comparativo()
        assert set(comparativo["dataset"]) == {
            "inventario", "transacciones", "feedback"}
        assert comparativo["filas_antes"].sum() == 17_000

    def test_el_reporte_de_limpieza_es_descargable(self, pipeline_limpieza):
        """Requisito de la guía: el usuario debe poder descargarlo."""
        csv = pipeline_limpieza.reporte_csv()
        assert "justificacion" in csv
        assert len(csv.splitlines()) > 20


class TestRobustezDeLaOrquestacion:
    """La app no debe caerse ante un filtro extremo."""

    def test_recorte_vacio_no_rompe_ninguna_capa(self, integrado):
        from datetime import date
        seleccion = filters.Filtros(fecha_desde=date(2030, 1, 1))
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        assert recorte.empty

        for funcion in (analytics.analizar_fuga_capital,
                        analytics.analizar_crisis_logistica,
                        analytics.analizar_paradoja_fidelidad,
                        analytics.analizar_riesgo_operativo):
            assert funcion(recorte).diagnostico

        with pytest.raises(ValueError, match="no contiene transacciones"):
            ai_insights.construir_resumen(recorte, seleccion.describir())

    @pytest.mark.parametrize("filas", [1, 5, 29])
    def test_muestras_minimas_degradan_sin_romperse(self, integrado, filas):
        """Por debajo del mínimo, ninguna prueba estadística es posible.

        El módulo debe declararlo en lugar de devolver un coeficiente
        calculado sobre tres puntos, que es exactamente el tipo de cifra que
        termina en una diapositiva sin su advertencia.
        """
        recorte = integrado.ssot.head(filas)
        q1 = analytics.analizar_fuga_capital(recorte)

        assert not q1.veredicto_pricing.significativo
        assert not q1.veredicto_pricing.concluyente
        assert q1.veredicto_pricing.lectura.strip()
        assert q1.diagnostico.strip()

    def test_los_filtros_son_hashables_para_el_cache(self):
        """Streamlit necesita claves hashables para cachear por recorte."""
        for seleccion in RECORTES.values():
            assert isinstance(hash(seleccion), int)

    def test_aplicar_filtros_no_muta_la_fuente(self, integrado):
        """Un filtro que mutara la SSOT corrompería el caché de Streamlit."""
        antes = len(integrado.ssot)
        columnas_antes = list(integrado.ssot.columns)
        filters.aplicar_filtros(integrado.ssot, RECORTES["combinado"])

        assert len(integrado.ssot) == antes
        assert list(integrado.ssot.columns) == columnas_antes

    def test_opciones_del_sidebar_provienen_de_datos_curados(self, integrado):
        """Criterio de aceptación: una opción coherente por entidad real."""
        opciones = filters.opciones_disponibles(integrado.ssot)

        assert len(opciones["canales"]) == 4
        assert len(opciones["bodegas"]) == 5
        for lista in (opciones["categorias"], opciones["bodegas"],
                      opciones["canales"]):
            assert all(isinstance(v, str) and v == v.strip() for v in lista)
        assert opciones["fecha_min"] < opciones["fecha_max"]


class TestContratoDeLasPestanas:
    """Cada módulo de pestaña debe exponer la interfaz que app.py espera."""

    def test_todas_exponen_renderizar(self):
        from ui.tabs import (auditoria, cliente, insights_ia, operaciones,
                             transparencia)
        for modulo in (auditoria, transparencia, operaciones, cliente,
                       insights_ia):
            assert callable(getattr(modulo, "renderizar", None)), (
                f"{modulo.__name__} no expone renderizar()")

    def test_las_pestanas_de_negocio_reciben_un_dataframe(self):
        """Firma esperada: (recorte, descripcion, ...)."""
        import inspect
        from ui.tabs import cliente, insights_ia, operaciones

        for modulo in (operaciones, cliente, insights_ia):
            parametros = list(
                inspect.signature(modulo.renderizar).parameters)
            assert parametros[0] == "recorte", (
                f"{modulo.__name__}.renderizar debe recibir el recorte primero")

    def test_la_curaduria_no_recibe_recorte(self):
        """Congela la decisión de alcance de Auditoría y Transparencia."""
        import inspect
        from ui.tabs import auditoria, transparencia

        for modulo in (auditoria, transparencia):
            parametros = list(
                inspect.signature(modulo.renderizar).parameters)
            assert parametros == ["resultado"], (
                f"{modulo.__name__} debe recibir la curaduría completa")

    def test_el_sidebar_expone_las_dos_funciones(self):
        from ui import sidebar
        assert callable(sidebar.construir)
        assert callable(sidebar.mostrar_alcance)
