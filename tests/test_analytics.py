"""Pruebas del análisis cruzado y del criterio de significancia.

El foco es que ningún hallazgo se declare sólido solo por su valor p. Con
muestras de miles de filas eso es trivialmente fácil y es justo el error que
llevaría a recomendarle a la junta una acción basada en ruido.
"""

import numpy as np
import pandas as pd
import pytest

from src import analytics, config, filters


# Las cinco preguntas se resuelven una vez por sesión y se comparten entre
# clases. Se definen a nivel de módulo y no dentro de cada clase porque una
# fixture de alcance de clase declarada como método de instancia está
# deprecada en pytest y dejará de funcionar en la versión 10.


@pytest.fixture(scope="session")
def q1(integrado):
    """Pregunta 1: fuga de capital, sobre la operación completa."""
    return analytics.analizar_fuga_capital(integrado.ssot)


@pytest.fixture(scope="session")
def q2(integrado):
    """Pregunta 2: crisis logística."""
    return analytics.analizar_crisis_logistica(integrado.ssot)


@pytest.fixture(scope="session")
def q3(integrado):
    """Pregunta 3: venta invisible."""
    return analytics.analizar_venta_invisible(
        integrado.ssot, integrado.diagnostico_fantasma)


@pytest.fixture(scope="session")
def q4(integrado):
    """Pregunta 4: paradoja de fidelidad."""
    return analytics.analizar_paradoja_fidelidad(integrado.ssot)


@pytest.fixture(scope="session")
def q5(integrado):
    """Pregunta 5: riesgo operativo."""
    return analytics.analizar_riesgo_operativo(integrado.ssot)


@pytest.fixture(scope="session")
def recorte_vacio(integrado):
    """Recorte que no deja ninguna transacción, para probar robustez."""
    from datetime import date
    seleccion = filters.Filtros(fecha_desde=date(2030, 1, 1))
    return filters.aplicar_filtros(integrado.ssot, seleccion)


class TestVeredicto:
    """Significancia y relevancia son condiciones distintas."""

    def _veredicto(self, p_valor, efecto):
        return analytics.Veredicto(
            pregunta="test", prueba="test", estadistico=1.0, p_valor=p_valor,
            n=8_000, tamano_efecto=efecto, nombre_efecto="efecto")

    def test_significativo_con_efecto_trivial_no_es_concluyente(self):
        """El caso real de la pregunta 1: p=0,0047 con V de Cramér=0,04."""
        veredicto = self._veredicto(0.0047, 0.04)
        assert veredicto.significativo
        assert veredicto.magnitud == "trivial"
        assert not veredicto.concluyente
        assert veredicto.etiqueta == "Significativo pero irrelevante"

    def test_significativo_con_efecto_real_si_concluye(self):
        veredicto = self._veredicto(0.001, 0.35)
        assert veredicto.concluyente
        assert veredicto.magnitud == "medio"
        assert veredicto.etiqueta == "Hallazgo sólido"

    def test_no_significativo_nunca_concluye(self):
        veredicto = self._veredicto(0.40, 0.60)
        assert not veredicto.significativo
        assert not veredicto.concluyente
        assert veredicto.etiqueta == "Sin evidencia"

    def test_efecto_negativo_se_evalua_en_magnitud(self):
        """Una correlación inversa fuerte es tan relevante como una directa."""
        veredicto = self._veredicto(0.001, -0.45)
        assert veredicto.magnitud == "medio"
        assert veredicto.concluyente

    def test_serializable(self):
        datos = self._veredicto(0.01, 0.2).a_dict()
        assert {"p_valor", "tamano_efecto", "magnitud", "concluyente"} \
            <= set(datos)


class TestPruebasEstadisticas:
    """Las pruebas deben degradar con elegancia, no reventar."""

    def test_correlacion_con_muestra_insuficiente(self):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]})
        veredicto = analytics.probar_correlacion(df, "x", "y", "test", "a", "b")
        assert not veredicto.significativo
        assert "insuficiente" in veredicto.lectura

    def test_correlacion_detecta_relacion_real(self):
        rng = np.random.default_rng(42)
        x = rng.normal(size=500)
        df = pd.DataFrame({"x": x, "y": x * 2 + rng.normal(scale=0.3, size=500)})
        veredicto = analytics.probar_correlacion(df, "x", "y", "test", "sí",
                                                 "no")
        assert veredicto.concluyente and veredicto.magnitud == "grande"

    def test_independencia_con_una_sola_categoria(self):
        df = pd.DataFrame({"g": ["a"] * 50, "b": [True, False] * 25})
        veredicto = analytics.probar_independencia(df, "g", "b", "test", "a",
                                                   "b")
        assert not veredicto.significativo

    def test_v_de_cramer_acotada(self):
        tabla = pd.crosstab(pd.Series(list("aabbcc") * 50),
                            pd.Series([True, False] * 150))
        valor = analytics._v_de_cramer(tabla, 10.0)
        assert 0.0 <= valor <= 1.0


class TestPregunta1FugaCapital:
    """Las dos hipótesis de la junta y la tercera que no consideró."""

    def test_kpis_completos(self, q1):
        esperados = {
            "skus_con_perdida", "perdida_total_usd", "pct_trx_con_perdida",
            "pct_perdida_antes_del_flete", "erosion_pct",
        }
        assert esperados <= set(q1.kpis)

    def test_perdida_coincide_con_la_suma_de_sku_deficitarios(self, q1):
        deficitarios = q1.por_sku[q1.por_sku["Es_Deficitario"]]
        assert q1.kpis["perdida_total_usd"] == pytest.approx(
            -deficitarios["margen_neto_usd"].sum(), abs=0.01)

    def test_hipotesis_loss_leader_se_descarta(self, q1):
        """Volumen y margen unitario son independientes: no hay gancho."""
        assert not q1.veredicto_volumen.concluyente
        assert abs(q1.veredicto_volumen.tamano_efecto) < 0.1

    def test_hipotesis_canal_online_se_descarta(self, q1):
        """El efecto del canal es detectable pero trivial, y Online no es peor."""
        assert q1.veredicto_canal.magnitud == "trivial"
        assert not q1.veredicto_canal.concluyente

        tasas = q1.por_canal.set_index("Canal_Venta")["tasa_negativa_pct"]
        assert tasas["Online"] < tasas.max(), (
            "Online no es el peor canal: la hipótesis de la junta se invierte")

    def test_causa_real_es_ausencia_de_pricing(self, q1):
        assert not q1.veredicto_pricing.concluyente
        assert abs(q1.veredicto_pricing.tamano_efecto) < 0.1
        assert "independiente" in q1.veredicto_pricing.lectura

    def test_el_flete_no_explica_la_perdida(self, q1):
        """98,6 % de las ventas deficitarias ya perdía antes de despachar."""
        assert q1.kpis["pct_perdida_antes_del_flete"] > 95
        assert q1.kpis["pct_perdida_por_flete"] < 5

    def test_perdida_difusa_no_concentrada(self, q1):
        """Sin Pareto, corregir SKU por SKU no resuelve el problema."""
        top50 = q1.pareto[q1.pareto["ranking"] <= 50]["pct_perdida"].max()
        assert top50 < 40, "La pérdida está repartida, no concentrada"

    def test_pareto_es_monotona_y_llega_a_cien(self, q1):
        pct = q1.pareto["pct_perdida"]
        assert pct.is_monotonic_increasing
        assert pct.iloc[-1] == pytest.approx(100.0)

    def test_fantasma_excluida_con_advertencia(self, q1):
        """Sin costo conocido no hay margen; debe avisarse, no ocultarse."""
        assert q1.advertencias
        assert "maestro" in q1.advertencias[0]

    def test_diagnostico_redactado(self, q1):
        assert len(q1.diagnostico) > 100
        assert "hipótesis" in q1.diagnostico.lower()


class TestFiltros:
    """El recorte debe ser puro y reproducible fuera de la interfaz."""

    def test_sin_filtros_devuelve_todo(self, integrado):
        vacio = filters.Filtros()
        assert not vacio.hay_filtro_activo
        assert len(filters.aplicar_filtros(integrado.ssot, vacio)) == 10_000

    def test_filtro_por_categoria(self, integrado):
        seleccion = filters.Filtros(categorias=("Laptops",))
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        assert (recorte["Categoria_Analisis"] == "Laptops").all()
        assert 0 < len(recorte) < 10_000

    def test_filtro_por_ciudad(self, integrado):
        seleccion = filters.Filtros(ciudades=("Medellín",))
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        assert (recorte["Ciudad_Destino"] == "Medellín").all()
        assert 0 < len(recorte) < 10_000

    def test_filtro_por_canal_y_categoria_se_combinan(self, integrado):
        seleccion = filters.Filtros(categorias=("Laptops",),
                                    canales=("Online",))
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        assert (recorte["Canal_Venta"] == "Online").all()
        assert (recorte["Categoria_Analisis"] == "Laptops").all()

    def test_excluir_venta_fantasma(self, integrado):
        seleccion = filters.Filtros(incluir_fantasma=False)
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        assert len(recorte) == 8_249
        assert not recorte[config.COL_FLAG_FANTASMA].any()

    def test_filtro_de_fechas(self, integrado):
        from datetime import date
        seleccion = filters.Filtros(fecha_desde=date(2025, 1, 1),
                                    fecha_hasta=date(2025, 12, 31))
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        assert recorte["Fecha_Venta"].min() >= pd.Timestamp("2025-01-01")
        assert recorte["Fecha_Venta"].max() <= pd.Timestamp("2025-12-31")

    def test_opciones_no_traen_variantes_sin_normalizar(self, integrado):
        """Criterio de aceptación: una opción coherente por entidad real."""
        opciones = filters.opciones_disponibles(integrado.ssot)
        assert "norte" not in opciones["bodegas"]
        assert "smart-phone" not in opciones["categorias"]
        assert "med" not in opciones["ciudades"]
        assert len(opciones["canales"]) == 4
        assert len(opciones["ciudades"]) == 5

    def test_descripcion_del_filtro(self):
        seleccion = filters.Filtros(categorias=("Laptops",),
                                    canales=("Online",))
        texto = seleccion.describir()
        assert "Laptops" in texto and "Online" in texto

    def test_filtros_son_hashables(self):
        """Requisito para usarlos como clave de caché."""
        assert hash(filters.Filtros(categorias=("a",))) is not None


class TestAnalisisBajoFiltro:
    """La pregunta 1 debe seguir siendo correcta sobre cualquier recorte."""

    def test_analisis_sobre_recorte_pequeno(self, integrado):
        seleccion = filters.Filtros(categorias=("Laptops",),
                                    canales=("Online",))
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        resultado = analytics.analizar_fuga_capital(recorte)

        assert resultado.kpis["perdida_total_usd"] > 0
        assert len(resultado.por_sku) <= len(recorte)

    def test_recorte_vacio_no_revienta(self, integrado):
        from datetime import date
        seleccion = filters.Filtros(fecha_desde=date(2030, 1, 1))
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        resultado = analytics.analizar_fuga_capital(recorte)

        assert recorte.empty
        assert resultado.kpis == {}
        assert "Sin transacciones" in resultado.diagnostico

    def test_solo_fantasma_no_deja_analisis_de_margen(self, integrado):
        """Sin costo no hay margen: el análisis debe vaciarse, no inventarlo."""
        solo_fantasma = integrado.ssot[integrado.ssot[config.COL_FLAG_FANTASMA]]
        resultado = analytics.analizar_fuga_capital(solo_fantasma)
        assert resultado.kpis == {}
        assert resultado.advertencias


class TestCorreccionMultiple:
    """Evaluar varios grupos y quedarse con el mejor es una trampa."""

    def test_bonferroni_multiplica_por_el_numero_de_comparaciones(self,
                                                                  integrado):
        tabla = analytics.correlaciones_por_grupo(
            integrado.ssot, "Ciudad_Destino", "Tiempo_Entrega_Real",
            "Satisfaccion_NPS")
        assert not tabla.empty
        esperado = (tabla["p_crudo"] * tabla["comparaciones"]).clip(upper=1.0)
        assert (tabla["p_corregido"] - esperado).abs().max() < 1e-9

    def test_p_corregido_nunca_supera_uno(self, integrado):
        tabla = analytics.correlaciones_por_grupo(
            integrado.ssot, "Bodega_Origen", "Tiempo_Entrega_Real",
            "Satisfaccion_NPS")
        assert (tabla["p_corregido"] <= 1.0).all()

    def test_grupos_pequenos_se_descartan(self):
        df = pd.DataFrame({"g": ["a"] * 5 + ["b"] * 200,
                           "x": range(205), "y": range(205)})
        tabla = analytics.correlaciones_por_grupo(df, "g", "x", "y")
        assert list(tabla["g"]) == ["b"], "El grupo de 5 filas debe excluirse"

    def test_sin_grupos_validos_devuelve_tabla_vacia(self):
        df = pd.DataFrame({"g": ["a"] * 5, "x": range(5), "y": range(5)})
        tabla = analytics.correlaciones_por_grupo(df, "g", "x", "y")
        assert tabla.empty
        assert "p_corregido" in tabla.columns


class TestPregunta2CrisisLogistica:
    """El NPS no discrimina: la respuesta se da en dos niveles."""

    def test_ninguna_correlacion_sobrevive_a_bonferroni(self, q2):
        assert q2.kpis["correlaciones_significativas"] == 0
        assert q2.kpis["correlaciones_evaluadas"] == 10

    def test_no_se_senala_zona_critica(self, q2):
        """Señalar una plaza sobre ruido sería el error grave de esta pregunta."""
        assert q2.zona_critica == "Ninguna zona destaca"
        assert "ninguna es peor" in q2.diagnostico.lower()

    def test_tasa_adversa_es_el_hallazgo_real(self, q2):
        """La cifra alarmante es el nivel absoluto, no la diferencia."""
        assert q2.kpis["tasa_envio_adverso_pct"] > 50

    def test_desempeno_cubre_las_cinco_plazas(self, q2):
        assert len(q2.desempeno_ciudad) == 5
        assert len(q2.desempeno_bodega) == 5

    def test_tasa_adversa_homogenea_entre_plazas(self, q2):
        amplitud = (q2.desempeno_ciudad["tasa_adversa"].max()
                    - q2.desempeno_ciudad["tasa_adversa"].min())
        assert amplitud < 10, "Las plazas no difieren de forma relevante"

    def test_veredictos_no_concluyentes(self, q2):
        assert not q2.veredicto_adversa.concluyente
        assert not q2.veredicto_tiempo.concluyente


class TestPregunta3VentaInvisible:
    """La única pregunta con hallazgo limpio y cuantificable."""

    def test_cifras_principales(self, q3):
        assert q3.kpis["transacciones"] == 1_751
        assert q3.kpis["skus"] == 480
        assert q3.kpis["pct_ingreso"] == pytest.approx(17.4, abs=0.1)

    def test_estima_el_margen_fuera_de_control(self, q3):
        """El ingreso es el síntoma; la utilidad no auditable es el daño."""
        assert q3.kpis["margen_no_controlado_usd"] > 0
        assert (q3.kpis["margen_no_controlado_usd"]
                < q3.kpis["ingreso_usd"]), "El margen no puede superar al ingreso"

    def test_serie_mensual_completa(self, q3):
        assert len(q3.serie_mensual) >= 12
        assert (q3.serie_mensual["pct_fantasma"] >= 0).all()

    def test_fuga_es_estructural_no_puntual(self, q3):
        """Un pico aislado sería un incidente; una meseta es un proceso roto."""
        assert q3.serie_mensual["pct_fantasma"].std() < 6

    def test_reparto_parejo_entre_canales(self, q3):
        """Concentración en un canal apuntaría a una integración rota."""
        pct = q3.por_canal["pct_fantasma"]
        assert pct.max() - pct.min() < 10

    def test_criterios_de_diagnostico_presentes(self, q3):
        assert len(q3.criterios_diagnostico) == 6
        assert "catálogo" in q3.veredicto_origen.lower()


class TestPregunta4ParadojaFidelidad:
    """La paradoja no existe porque nada difiere entre categorías."""

    def test_sentimiento_no_difiere(self, q4):
        assert not q4.veredicto_sentimiento.concluyente

    def test_stock_no_difiere(self, q4):
        assert not q4.veredicto_stock.concluyente

    def test_paradoja_se_descarta_en_el_diagnostico(self, q4):
        assert "no se sostiene" in q4.diagnostico.lower()

    def test_causa_dominante_es_precio(self, q4):
        """Responde la disyuntiva del enunciado: sobrecosto, no calidad."""
        assert q4.kpis["causa_dominante"] == "Precio/Valor"
        assert q4.kpis["pct_causa_dominante"] > 33

    def test_causa_raiz_suma_cien_por_categoria(self, q4):
        numericas = q4.causa_raiz.select_dtypes("number")
        assert (numericas.sum(axis=1) - 100).abs().max() < 0.5

    def test_separa_fantasma_de_sin_clasificar(self, q4):
        categorias = set(q4.por_categoria["Categoria_Analisis"])
        assert config.ETIQUETA_SIN_CATALOGO in categorias
        assert "Sin_Clasificar" in categorias

    def test_feedback_no_confiable_excluido_del_rating(self, q4, integrado):
        """767 transacciones con feedback de varios clientes no deben
        contaminar el veredicto de calificación por categoría."""
        assert q4.advertencias, (
            "Debe advertirse que hay feedback colapsado excluido")
        assert "767" in q4.advertencias[0]

        ssot = integrado.ssot
        no_confiables = ssot[ssot["Feedback_Confiable"] == False]  # noqa: E712
        assert q4.veredicto_sentimiento.n <= (
            ssot["Rating_Producto"].notna().sum()
            - no_confiables["Rating_Producto"].notna().sum())


class TestPregunta5RiesgoOperativo:
    """La ceguera de inventario es real; su castigo aún no aparece."""

    def test_antiguedad_alarmante(self, q5):
        assert q5.kpis["antiguedad_meses"] > 12, (
            "Más de un ciclo anual sin verificar el inventario físico")

    def test_tickets_no_difieren_entre_bodegas(self, q5):
        assert not q5.veredicto_tickets_bodega.concluyente

    def test_sin_correlacion_antiguedad_tickets(self, q5):
        assert not q5.veredicto_antiguedad_tickets.concluyente
        assert abs(q5.veredicto_antiguedad_tickets.tamano_efecto) < 0.1

    def test_diagnostico_no_concluye_ausencia_de_riesgo(self, q5):
        """Ausencia de evidencia no es evidencia de ausencia."""
        texto = q5.diagnostico.lower()
        assert "a ciegas" in texto or "no se ha cobrado" in texto

    def test_marca_bodegas_no_estandar(self, q5):
        no_estandar = q5.por_bodega[q5.por_bodega["Nomenclatura_No_Estandar"]]
        assert set(no_estandar["Bodega_Origen"]) == set(
            config.BODEGAS_NO_ESTANDAR)

    def test_cubre_las_cinco_bodegas(self, q5):
        assert len(q5.por_bodega) == 5
        assert q5.por_bodega["antiguedad_mediana"].notna().all()


class TestRobustezBajoFiltro:
    """Ninguna pregunta puede reventar con un recorte extremo."""

    def test_todas_las_preguntas_toleran_recorte_vacio(
            self, recorte_vacio, integrado):
        assert recorte_vacio.empty
        for funcion in (analytics.analizar_fuga_capital,
                        analytics.analizar_crisis_logistica,
                        analytics.analizar_paradoja_fidelidad,
                        analytics.analizar_riesgo_operativo):
            resultado = funcion(recorte_vacio)
            assert resultado.diagnostico

        invisible = analytics.analizar_venta_invisible(
            recorte_vacio, integrado.diagnostico_fantasma)
        assert invisible.kpis == {}

    def test_una_sola_ciudad_no_permite_comparar(self, integrado):
        una = integrado.ssot[integrado.ssot["Ciudad_Destino"] == "Cali"]
        resultado = analytics.analizar_crisis_logistica(una)
        assert len(resultado.correlaciones_ciudad) <= 1
        assert resultado.kpis["correlaciones_significativas"] == 0

    def test_preguntas_responden_al_filtro(self, integrado):
        """El recorte debe cambiar las cifras, no ignorarse."""
        seleccion = filters.Filtros(canales=("Online",))
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)

        completo = analytics.analizar_venta_invisible(integrado.ssot)
        filtrado = analytics.analizar_venta_invisible(recorte)
        assert filtrado.kpis["ingreso_usd"] < completo.kpis["ingreso_usd"]
