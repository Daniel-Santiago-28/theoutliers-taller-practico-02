"""Pruebas de la integración y de la Sola Fuente de Verdad.

El foco es la preservación del grano: casi todos los errores graves de esta
fase son silenciosos —una fila que se duplica, un ingreso que se cuenta dos
veces— y solo se detectan reconciliando contra el archivo original.
"""

import pandas as pd
import pytest

from src import config, integration


@pytest.fixture(scope="session")
def limpios(pipeline_limpieza):
    """Alias local del pipeline compartido definido en conftest."""
    return pipeline_limpieza


class TestPreservacionDelGrano:
    """El fan-out es el riesgo central de esta fase."""

    def test_ssot_conserva_el_grano_de_transaccion(self, integrado, limpios):
        assert len(integrado.ssot) == len(limpios.limpios["transacciones"])
        assert len(integrado.ssot) == 10_000
        assert integrado.ssot["Transaccion_ID"].is_unique

    def test_feedback_se_agrega_antes_de_unir(self, limpios):
        agregado = integration.agregar_feedback_a_transaccion(
            limpios.limpios["feedback"])
        assert len(agregado) == 3_623
        assert agregado["Transaccion_ID"].is_unique
        assert int(agregado["N_Opiniones"].sum()) == 4_500

    def test_merge_ingenuo_si_inflaria_el_ingreso(self, limpios):
        """Documenta el problema que la agregación previa evita.

        Si este test dejara de fallar el fan-out, significaría que el dataset
        cambió y que la agregación previa ya no es necesaria.
        """
        trx = limpios.limpios["transacciones"]
        fbk = limpios.limpios["feedback"]
        ingenuo = trx.merge(fbk, on="Transaccion_ID", how="left")

        ingreso = lambda d: float(  # noqa: E731
            (d["Precio_Venta_Final"] * d["Cantidad_Vendida"]).sum())
        assert len(ingenuo) > len(trx), "Debe haber fan-out sin agregación"
        assert ingreso(ingenuo) > ingreso(trx) * 1.05

    def test_ningun_sku_duplica_la_venta(self, integrado):
        """El maestro es 1:1 por SKU; si no, el merge multiplicaría ventas."""
        assert integrado.ssot["Transaccion_ID"].nunique() == 10_000

    def test_opiniones_conserva_el_grano_original(self, integrado):
        assert len(integrado.opiniones) == 4_500


class TestTrazabilidad:
    """Criterio de aceptación: el ingreso debe ser trazable al original."""

    def test_reconciliacion_exacta(self, integrado):
        rec = integrado.reconciliacion
        assert rec.cuadra
        assert abs(rec.diferencia) <= integration.TOLERANCIA_RECONCILIACION

    def test_ingreso_coincide_con_el_archivo_original(self, integrado,
                                                      datos_crudos):
        """Reconciliación calculada de forma independiente al módulo."""
        crudo = datos_crudos["transacciones"]
        precio = pd.to_numeric(crudo["Precio_Venta_Final"], errors="coerce")
        cantidad = pd.to_numeric(crudo["Cantidad_Vendida"], errors="coerce")
        validas = cantidad > 0
        esperado = float((precio[validas] * cantidad[validas]).sum())

        assert integrado.ssot["Ingreso_Bruto"].sum() == pytest.approx(
            esperado, abs=integration.TOLERANCIA_RECONCILIACION)

    def test_diferencia_con_el_bruto_son_las_cantidades_invalidas(
            self, integrado):
        """El delta contra el crudo bruto debe explicarse por completo."""
        rec = integrado.reconciliacion
        assert rec.ingreso_crudo_valido > rec.ingreso_crudo_bruto, (
            "Las 100 cantidades negativas restaban ingreso")

    def test_reconciliacion_detecta_un_fan_out_inyectado(self, integrado,
                                                         datos_crudos):
        """La validación debe fallar ruidosamente si alguien rompe el grano."""
        inflada = pd.concat([integrado.ssot, integrado.ssot.head(50)])
        with pytest.raises(integration.ReconciliacionFallida,
                           match="no cuadra"):
            integration.validar_trazabilidad(inflada,
                                             datos_crudos["transacciones"])


class TestVentaFantasma:
    """El dilema del SKU fantasma y su cuantificación."""

    def test_ventas_fantasma_marcadas_no_descartadas(self, integrado):
        ssot = integrado.ssot
        assert int(ssot[config.COL_FLAG_FANTASMA].sum()) == 1_751
        fantasma = ssot[ssot[config.COL_FLAG_FANTASMA]]
        assert (fantasma["Origen_Catalogo"]
                == config.ETIQUETA_SIN_CATALOGO).all()
        assert fantasma["Ingreso_Bruto"].notna().sum() > 0, (
            "El ingreso fantasma debe seguir contabilizado")

    def test_fantasma_sin_margen_calculado(self, integrado):
        """Sin costo conocido no puede haber margen: debe ser nulo, no cero."""
        fantasma = integrado.ssot[integrado.ssot[config.COL_FLAG_FANTASMA]]
        assert fantasma["Costo_Unitario_USD"].isna().all()
        assert fantasma["Margen_Neto"].isna().all()

    def test_resumen_para_la_pregunta_tres(self, integrado):
        resumen = integrado.resumen_fantasma()
        assert resumen["transacciones_fantasma"] == 1_751
        assert resumen["skus_fantasma"] == 480
        assert resumen["pct_ingreso_en_riesgo"] == pytest.approx(17.4, abs=0.1)

    def test_veredicto_es_falla_de_catalogo(self, integrado):
        diagnostico = integrado.diagnostico_fantasma
        assert "catálogo" in diagnostico["veredicto"].lower()
        assert diagnostico["criterios_a_favor_catalogo"] >= 5

    def test_criterios_del_diagnostico_documentados(self, integrado):
        criterios = integrado.diagnostico_fantasma["criterios"]
        assert {"contiguidad", "posicion", "volumen", "temporalidad",
                "precio", "canal"} == set(criterios)
        for nombre, detalle in criterios.items():
            assert detalle["prueba"], f"{nombre} sin evidencia"
            assert detalle["apunta_a"] in {"catálogo", "digitación"}

    def test_bloque_contiguo(self, integrado):
        """La contigüidad es lo que descarta el error de digitación."""
        contiguidad = (integrado.diagnostico_fantasma["criterios"]
                       ["contiguidad"])
        assert contiguidad["densidad_pct"] > 90
        assert contiguidad["salto_maximo"] <= 3


class TestVariablesDerivadas:
    """Las métricas de negocio que alimentan las cinco preguntas."""

    @pytest.mark.parametrize("columna", [
        "Ingreso_Bruto", "Margen_Unitario", "Margen_Neto", "Margen_Pct",
        "Brecha_Vs_Lead_Time", "Brecha_Vs_Benchmark", "Entrega_Adversa",
        "Ratio_Soporte_Categoria_Pct", "Categoria_Analisis", "N_Opiniones",
    ])
    def test_variable_existe(self, integrado, columna):
        assert columna in integrado.ssot.columns

    def test_margen_neto_descuenta_el_flete(self, integrado):
        ssot = integrado.ssot
        fila = ssot[ssot["Margen_Neto"].notna()].iloc[0]
        esperado = (fila["Margen_Unitario"] * fila["Cantidad_Vendida"]
                    - fila["Costo_Envio"])
        assert fila["Margen_Neto"] == pytest.approx(esperado)

    def test_ingreso_bruto_es_precio_por_cantidad(self, integrado):
        ssot = integrado.ssot[integrado.ssot["Ingreso_Bruto"].notna()]
        esperado = ssot["Precio_Venta_Final"] * ssot["Cantidad_Vendida"]
        assert (ssot["Ingreso_Bruto"] - esperado).abs().max() < 1e-6

    def test_categoria_analisis_separa_fantasma_de_sin_clasificar(
            self, integrado):
        """Dos fallas de negocio distintas no pueden agregarse juntas."""
        ssot = integrado.ssot
        conteo = ssot["Categoria_Analisis"].value_counts()
        assert conteo[config.ETIQUETA_SIN_CATALOGO] == 1_751
        assert conteo["Sin_Clasificar"] == 1_043
        assert ssot["Categoria_Analisis"].isna().sum() == 0

    def test_brecha_benchmark_centrada_en_cero(self, integrado):
        """Por construcción, la mediana de la brecha contra la propia plaza
        debe ser cero: es una desviación respecto a la mediana local."""
        brecha = integrado.ssot["Brecha_Vs_Benchmark"].dropna()
        assert brecha.median() == pytest.approx(0.0, abs=0.5)

    def test_ratio_soporte_usa_denominador_con_opinion(self, integrado):
        tabla = integrado.ratio_soporte
        assert (tabla["ventas_con_opinion"] <= tabla["ventas_totales"]).all()
        assert (tabla["ratio_soporte_pct"] <= 100).all()


class TestAgregacionDeFeedback:
    """Las reglas de colapso deben respetar la naturaleza de cada variable."""

    def test_ticket_usa_maximo_no_promedio(self, limpios):
        """Un ticket es un hecho operativo: si alguien lo abrió, existió."""
        fbk = limpios.limpios["feedback"]
        agregado = integration.agregar_feedback_a_transaccion(fbk)

        multi = fbk.groupby("Transaccion_ID")["Ticket_Soporte_Abierto"].any()
        fusion = agregado.set_index("Transaccion_ID")["Ticket_Soporte_Abierto"]
        assert (fusion == multi.reindex(fusion.index)).all()

    def test_ratings_usan_promedio(self, limpios):
        fbk = limpios.limpios["feedback"]
        agregado = integration.agregar_feedback_a_transaccion(fbk)
        esperado = fbk.groupby("Transaccion_ID")["Rating_Logistica"].mean()
        fusion = agregado.set_index("Transaccion_ID")["Rating_Logistica"]
        assert (fusion - esperado.reindex(fusion.index)).abs().max() < 1e-9

    def test_moda_es_determinista(self):
        """Ante empate gana el menor alfabéticamente, no el orden de llegada."""
        df = pd.DataFrame({
            "k": ["t1", "t1", "t1", "t1", "t2", "t2", "t2"],
            "v": ["b", "a", "b", "a", "z", "z", "y"],
        })
        moda = integration.moda_por_grupo(df, "k", "v")
        assert moda["t1"] == "a", "Empate 2-2 debe resolverse alfabéticamente"
        assert moda["t2"] == "z", "Sin empate gana la mayoría"

    def test_moda_ignora_nulos_y_grupos_vacios(self):
        df = pd.DataFrame({"k": ["t1", "t1", "t2"],
                           "v": [None, "a", None]})
        moda = integration.moda_por_grupo(df, "k", "v")
        assert moda["t1"] == "a"
        assert "t2" not in moda.index, "Un grupo sin valores no tiene moda"

        vacio = pd.DataFrame({"k": [], "v": []})
        assert integration.moda_por_grupo(vacio, "k", "v").empty


class TestPoliticaDePrecios:
    """Da sentido, o se lo quita, al conteo de márgenes negativos."""

    def test_diagnostico_completo(self, integrado):
        politica = integrado.politica_precios
        assert politica["n"] > 8_000
        assert "spearman_rho" in politica and "veredicto" in politica

    def test_precio_desacoplado_del_costo(self, integrado):
        """Hallazgo central de la pregunta 1: no hay función de pricing."""
        politica = integrado.politica_precios
        assert abs(politica["spearman_rho"]) < 0.05
        assert not politica["significativo"]
        assert "independencia" in politica["veredicto"]


class TestManejoDeErrores:
    """La integración debe fallar ruidosamente, nunca en silencio."""

    def test_falta_dataset(self, limpios):
        with pytest.raises(integration.ErrorIntegracion, match="Faltan"):
            integration.construir_ssot({"transacciones": pd.DataFrame()})

    def test_inventario_duplicado_rompe_el_merge(self, limpios):
        """validate='m:1' debe atrapar un maestro con SKU repetidos."""
        corrupto = dict(limpios.limpios)
        inventario = corrupto["inventario"]
        corrupto["inventario"] = pd.concat([inventario, inventario.head(5)])
        with pytest.raises((pd.errors.MergeError, integration.ErrorIntegracion)):
            integration.construir_ssot(corrupto, limpios.crudos)
