"""Pruebas de la limpieza y de la auditoría de calidad.

Verifican los casos de prueba de la Guía de Validación del challenge y
congelan las decisiones de curaduría, de modo que una refactorización futura
no pueda alterarlas en silencio.
"""

import json
from datetime import datetime

import pandas as pd
import pytest

from src import audit, cleaning, config


@pytest.fixture(scope="module")
def resultado(datos_crudos):
    """Pipeline completo con la política de duplicados recomendada."""
    return cleaning.ejecutar_pipeline(datos_crudos)


class TestHealthScore:
    """El módulo de transparencia debe mostrar una mejora medible."""

    @pytest.mark.parametrize(
        "dataset", ["inventario", "transacciones", "feedback"])
    def test_score_mejora(self, resultado, dataset):
        antes = resultado.scores_antes[dataset].total
        despues = resultado.scores_despues[dataset].total
        assert despues > antes, f"{dataset} no mejoró: {antes} -> {despues}"

    @pytest.mark.parametrize(
        "dataset", ["inventario", "transacciones", "feedback"])
    def test_validez_y_consistencia_quedan_perfectas(self, resultado, dataset):
        dims = resultado.scores_despues[dataset].dimensiones
        assert dims["consistencia"].pct == 100.0
        assert dims["validez"].pct >= 99.0

    def test_score_acotado(self, resultado):
        for score in list(resultado.scores_antes.values()) + \
                list(resultado.scores_despues.values()):
            assert 0.0 <= score.total <= 100.0

    def test_score_es_comparable_entre_momentos(self, resultado):
        """Antes y después deben medirse sobre el mismo conjunto de columnas."""
        for nombre in resultado.crudos:
            assert (resultado.scores_antes[nombre].columnas
                    == resultado.scores_despues[nombre].columnas)

    def test_dataset_vacio_falla(self):
        with pytest.raises(ValueError, match="vacío"):
            audit.calcular_health_score(pd.DataFrame(), "inventario", "antes")


class TestInventario:
    """Casos de prueba de robustez analítica sobre el maestro de productos."""

    def test_stock_negativo_truncado_y_marcado(self, resultado):
        inv = resultado.limpios["inventario"]
        assert (inv["Stock_Actual"] >= 0).all()
        assert int(inv["Stock_Negativo_Corregido"].sum()) == 60
        assert len(resultado.registro.excluidos["inventario_stock_negativo"]) == 60

    def test_costos_atipicos_excluidos_no_borrados(self, resultado):
        """Guía de validación: los KPIs no deben distorsionarse, pero el
        dashboard debe poder mostrar los registros excluidos."""
        inv = resultado.limpios["inventario"]
        assert len(inv) == 2_500, "No se debe perder ninguna fila del maestro"
        assert int(inv["Costo_Atipico_Excluido"].sum()) == 2
        assert inv.loc[inv["Costo_Atipico_Excluido"], "Costo_Unitario_USD"] \
            .isna().all()

        excluidos = resultado.registro.excluidos["inventario_costo_atipico"]
        assert len(excluidos) == 2
        assert "motivo_exclusion" in excluidos.columns
        costos = pd.to_numeric(excluidos["Costo_Unitario_USD"])
        assert costos.max() == 850_000.0 and costos.min() == 0.05

    def test_categorias_unificadas(self, resultado):
        """Criterio de aceptación: una sola opción coherente por categoría."""
        categorias = set(resultado.limpios["inventario"]["Categoria"].dropna())
        assert categorias == {"Smartphones", "Laptops", "Monitores",
                              "Tablets", "Accesorios"}

    def test_bodegas_unificadas(self, resultado):
        bodegas = set(resultado.limpios["inventario"]["Bodega_Origen"].dropna())
        assert bodegas == {"Norte", "Sur", "Occidente", "Zona_Franca",
                           "BOD-EXT-99"}

    def test_lead_time_convertido(self, resultado):
        lead = resultado.limpios["inventario"]["Lead_Time_Dias"]
        assert lead.isna().sum() == 0
        assert 27.5 in set(lead), "El punto medio del intervalo debe existir"
        assert 0.0 in set(lead), "'Inmediato' debe mapear a cero días"

    def test_categoria_no_se_imputa(self, resultado):
        """Imputar una nominal casi uniforme fabricaría señal."""
        inv = resultado.limpios["inventario"]
        assert int(inv["Categoria"].isna().sum()) == 305


class TestTransacciones:
    """Casos de prueba sobre el histórico de ventas."""

    def test_centinela_999_eliminado(self, resultado):
        trx = resultado.limpios["transacciones"]
        assert trx["Tiempo_Entrega_Real"].max() <= \
            config.MAX_DIAS_ENTREGA_PLAUSIBLE
        assert int(trx["Entrega_Codigo_Error"].sum()) == 50

    def test_fechas_futuras_marcadas_no_borradas(self, resultado):
        """Guía: la serie de tiempo no debe mostrar actividad fuera del
        periodo real, pero el ingreso debe seguir siendo trazable.

        La aserción se hace contra ``datetime.now()`` y no contra un conteo
        fijo: la validación temporal es relativa al momento de ejecución, así
        que un número quemado convertiría este test en una bomba de tiempo.
        """
        trx = resultado.limpios["transacciones"]
        assert len(trx) == 10_000, "No se debe perder ninguna transacción"

        hoy = pd.Timestamp(config.fecha_corte())
        esperadas = int((trx["Fecha_Venta"] > hoy).sum())
        assert int(trx["Fecha_Futura"].sum()) == esperadas

        vigentes = trx.loc[~trx["Fecha_Futura"], "Fecha_Venta"]
        assert vigentes.max() <= hoy

    def test_fecha_corte_es_el_momento_de_ejecucion(self):
        """La fecha de referencia se evalúa en cada llamada, no al importar."""
        assert config.fecha_corte() == datetime.now().date()

    def test_ciudades_normalizadas(self, resultado):
        ciudades = set(resultado.limpios["transacciones"]["Ciudad_Destino"]
                       .dropna())
        assert ciudades == {"Medellín", "Bogotá", "Cali", "Barranquilla",
                            "Bucaramanga"}

    def test_ventas_web_sin_geografia_pero_conservadas(self, resultado):
        trx = resultado.limpios["transacciones"]
        sin_geo = trx[config.COL_FLAG_SIN_GEO]
        assert int(sin_geo.sum()) == 1_290
        assert trx.loc[sin_geo, "Ciudad_Destino"].isna().all()
        assert trx.loc[sin_geo, "Precio_Venta_Final"].notna().all(), \
            "El ingreso debe seguir siendo trazable"

    def test_cantidad_negativa_anulada_sin_imputar(self, resultado):
        trx = resultado.limpios["transacciones"]
        assert int(trx["Cantidad_Invalida"].sum()) == 100
        assert trx.loc[trx["Cantidad_Invalida"], "Cantidad_Vendida"].isna().all()
        assert (trx["Cantidad_Vendida"].dropna() > 0).all()

    def test_estado_envio_no_se_imputa(self, resultado):
        assert int(resultado.limpios["transacciones"]["Estado_Envio"]
                   .isna().sum()) == 1_683


class TestFeedback:
    """La voz del cliente: llave colisionada y codificaciones mixtas."""

    def test_politica_conservar_no_pierde_opiniones(self, resultado):
        fbk = resultado.limpios["feedback"]
        assert len(fbk) == 4_500
        assert fbk["Feedback_UID"].is_unique
        assert int(fbk["Feedback_ID_Colisionado"].sum()) == 969

    def test_politica_eliminar_descarta_lo_esperado(self, datos_crudos):
        limpio, log = cleaning.limpiar_feedback(
            datos_crudos["feedback"], politica_duplicados="eliminar")
        assert len(limpio) == 4_000
        assert limpio["Feedback_ID"].is_unique
        assert len(log.excluidos["feedback_id_colisionado_eliminado"]) == 500

    def test_politica_invalida_falla(self, datos_crudos):
        with pytest.raises(ValueError, match="no reconocida"):
            cleaning.limpiar_feedback(datos_crudos["feedback"],
                                      politica_duplicados="borrar_todo")

    def test_ticket_soporte_unificado(self, resultado):
        """Sin unificar Sí/No con 1/0 se contaría la mitad de los tickets."""
        ticket = resultado.limpios["feedback"]["Ticket_Soporte_Abierto"]
        assert ticket.isna().sum() == 0
        assert set(ticket.unique()) == {True, False}

    def test_ratings_fuera_de_escala_anulados(self, resultado):
        rating = resultado.limpios["feedback"]["Rating_Producto"]
        assert int(rating.isna().sum()) == 30
        assert rating.dropna().between(*config.RANGO_RATING).all()

    def test_edades_imposibles_corregidas(self, resultado):
        edad = resultado.limpios["feedback"]["Edad_Cliente"]
        assert edad.max() <= config.RANGO_EDAD_CLIENTE[1]
        assert edad.isna().sum() == 0, "La edad sí se imputa (distribución simétrica)"

    def test_segmentacion_nps(self, resultado):
        segmentos = set(resultado.limpios["feedback"][config.COL_SEGMENTO_NPS]
                        .dropna())
        assert segmentos == {"Detractor", "Pasivo", "Promotor"}

    def test_derivacion_causa_queja(self, resultado):
        """La causa raíz es lo que separa 'mala calidad' de 'sobrecosto'."""
        causas = set(resultado.limpios["feedback"]["Causa_Queja"].dropna())
        assert {"Calidad", "Logística", "Precio/Valor"} <= causas


class TestEstrategiaDeImputacion:
    """La estrategia debe derivarse de la distribución, no asumirse."""

    def test_simetrica_usa_media(self):
        simetrica = pd.Series(range(1, 1_001))
        estrategia, valor, evidencia = cleaning._elegir_estrategia(simetrica)
        assert estrategia == "media"
        assert "simétrica" in evidencia

    def test_sesgada_usa_mediana(self):
        sesgada = pd.Series([1] * 900 + [500] * 100)
        estrategia, valor, evidencia = cleaning._elegir_estrategia(sesgada)
        assert estrategia == "mediana"
        assert "sesgada" in evidencia

    def test_serie_vacia_no_imputa(self):
        estrategia, _, _ = cleaning._elegir_estrategia(
            pd.Series([], dtype=float))
        assert estrategia == "ninguna"

    def test_entropia_detecta_uniformidad(self):
        uniforme = pd.Series(list("abcde") * 100)
        concentrada = pd.Series(["a"] * 490 + list("bcde") * 2)
        assert cleaning._entropia_normalizada(uniforme) > 0.99
        assert cleaning._entropia_normalizada(concentrada) < 0.5

    def test_cada_imputacion_registra_su_evidencia(self, resultado):
        """Sin evidencia estadística la decisión no es defendible."""
        imputaciones = [a for a in resultado.registro.acciones
                        if a.accion.startswith("Imputación")]
        assert imputaciones, "Debe haber al menos una imputación registrada"
        for accion in imputaciones:
            assert "asimetría=" in accion.evidencia
            assert accion.justificacion and accion.valor_aplicado


class TestTrazabilidadDeImputaciones:
    """Un valor estimado nunca debe ser indistinguible de uno observado."""

    ESPERADAS = {
        "inventario": {"Stock_Actual_Imputado": 100,
                       "Lead_Time_Dias_Imputado": 403},
        "transacciones": {"Costo_Envio_Imputado": 834,
                          "Tiempo_Entrega_Real_Imputado": 50},
        "feedback": {"Edad_Cliente_Imputado": 23},
    }

    @pytest.mark.parametrize("dataset,banderas", ESPERADAS.items())
    def test_banderas_presentes_y_exactas(self, resultado, dataset, banderas):
        df = resultado.limpios[dataset]
        for bandera, esperado in banderas.items():
            assert bandera in df.columns, f"Falta la bandera {bandera}"
            assert int(df[bandera].sum()) == esperado

    def test_toda_imputacion_registrada_tiene_bandera(self, resultado):
        """Ninguna imputación de la bitácora puede quedar sin marcar."""
        for accion in resultado.registro.acciones:
            if not accion.accion.startswith("Imputación"):
                continue
            df = resultado.limpios[accion.dataset]
            bandera = cleaning.sufijo_imputado(accion.columna)
            assert bandera in df.columns
            assert int(df[bandera].sum()) == accion.filas_afectadas

    def test_bandera_coincide_con_el_valor_imputado(self, resultado):
        """Las filas marcadas deben llevar exactamente el valor estimado."""
        trx = resultado.limpios["transacciones"]
        imputados = trx.loc[trx["Costo_Envio_Imputado"], "Costo_Envio"]
        assert imputados.nunique() == 1, "Todas comparten el mismo estimador"
        assert imputados.notna().all()

    def test_permite_analizar_solo_lo_observado(self, resultado):
        """El caso de uso de la bandera: recuperar la dispersión original."""
        trx = resultado.limpios["transacciones"]
        observados = trx.loc[~trx["Costo_Envio_Imputado"], "Costo_Envio"]
        assert len(observados) == 9_166
        # La imputación por media contrae la varianza; sin la bandera esa
        # atenuación sería invisible y sesgaría cualquier correlación.
        assert observados.std() > trx["Costo_Envio"].std()

    def test_ratings_fuera_de_escala_marcados(self, resultado):
        fbk = resultado.limpios["feedback"]
        assert int(fbk["Rating_Producto_Fuera_Escala"].sum()) == 30
        assert fbk.loc[fbk["Rating_Producto_Fuera_Escala"],
                       "Rating_Producto"].isna().all()

    def test_banderas_no_afectan_el_health_score(self, resultado):
        """El score se mide sobre el esquema original, no sobre las derivadas."""
        for nombre in resultado.crudos:
            assert (resultado.scores_despues[nombre].columnas
                    == len(config.ESQUEMAS[nombre]))


class TestReporteDeLimpieza:
    """El reporte descargable es el entregable de transparencia."""

    def test_reporte_serializable_a_json(self, resultado):
        crudo = json.dumps(resultado.reporte_dict(), ensure_ascii=False,
                           default=str)
        assert "decisiones" in crudo and "resumen_por_dataset" in crudo

    def test_reporte_csv_no_vacio(self, resultado):
        csv = resultado.reporte_csv()
        assert "justificacion" in csv
        assert len(csv.splitlines()) > 20

    def test_comparativo_cubre_los_tres_datasets(self, resultado):
        comp = resultado.comparativo()
        assert len(comp) == 3
        assert {"health_score_antes", "health_score_despues",
                "filas_eliminadas"} <= set(comp.columns)

    def test_registros_excluidos_recuperables(self, resultado):
        """'No los borres en silencio': todo excluido debe ser consultable."""
        excluidos = resultado.registro.excluidos
        assert excluidos, "Debe haber registros excluidos archivados"
        for etiqueta, frame in excluidos.items():
            assert isinstance(frame, pd.DataFrame) and not frame.empty
