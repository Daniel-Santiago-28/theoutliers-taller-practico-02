"""Pruebas de la capa de ingesta y de la línea base forense.

Estos tests congelan los hechos medidos en el perfilado inicial. Si el archivo
fuente cambia o si una futura refactorización altera silenciosamente la lectura,
fallan aquí y no en las conclusiones que ve la junta directiva.
"""

import pandas as pd
import pytest

from src import config, ingest

# Línea base verificada con scripts/perfilado_inicial.py sobre los CSV
# originales entregados por el docente.
FILAS_ESPERADAS = {"inventario": 2_500, "transacciones": 10_000, "feedback": 4_500}


class TestIngesta:
    """Contrato de carga de los archivos fuente."""

    @pytest.mark.parametrize("nombre,filas", FILAS_ESPERADAS.items())
    def test_dimensiones_esperadas(self, datos_crudos, nombre, filas):
        assert len(datos_crudos[nombre]) == filas

    @pytest.mark.parametrize("nombre", list(FILAS_ESPERADAS))
    def test_esquema_completo(self, datos_crudos, nombre):
        assert list(datos_crudos[nombre].columns) == config.ESQUEMAS[nombre]

    @pytest.mark.parametrize("nombre", list(FILAS_ESPERADAS))
    def test_lectura_sin_coercion(self, datos_crudos, nombre):
        """La ingesta forense no debe convertir tipos ni interpretar nulos.

        Se valida contra ``is_string_dtype`` y no contra ``object``: pandas
        moderno respalda las columnas de texto con el dtype ``str`` nativo,
        de modo que comparar con ``object`` daría un falso negativo.
        """
        df = datos_crudos[nombre]
        no_texto = [
            col for col in df.columns
            if not pd.api.types.is_string_dtype(df[col])
        ]
        assert not no_texto, f"La ingesta alteró tipos en: {no_texto}"
        assert not df.isna().any().any(), "La ingesta interpretó nulos"

    def test_dataset_desconocido_falla(self):
        with pytest.raises(ValueError, match="Dataset desconocido"):
            ingest.cargar_crudo("ventas_marte")

    def test_esquema_invalido_falla(self):
        df = pd.DataFrame({"columna_ajena": [1, 2]})
        with pytest.raises(ingest.EsquemaInvalido, match="columnas obligatorias"):
            ingest.validar_esquema(df, "inventario")


class TestLineaBaseForense:
    """Hechos de calidad medidos antes de limpiar. Alimentan la Transparencia."""

    def test_centinelas_de_nulos_presentes(self, datos_crudos):
        """'???' y 'nan' son ausencias disfrazadas, no categorías reales."""
        inv = datos_crudos["inventario"]
        assert (inv["Categoria"] == "???").sum() == 305
        assert (inv["Lead_Time_Dias"] == "nan").sum() == 403

    def test_duplicados_de_feedback(self, datos_crudos):
        fbk = datos_crudos["feedback"]
        assert fbk["Feedback_ID"].duplicated().sum() == 500
        assert fbk.duplicated().sum() == 0, "Los duplicados no son filas idénticas"

    def test_ventas_fantasma(self, datos_crudos):
        """17,51 % de las ventas apuntan a SKU fuera del maestro."""
        catalogo = set(datos_crudos["inventario"]["SKU_ID"])
        huerfanas = ~datos_crudos["transacciones"]["SKU_ID"].isin(catalogo)
        assert huerfanas.sum() == 1_751

    def test_huerfanos_forman_bloque_contiguo(self, datos_crudos):
        """Evidencia de falla de catálogo, no de digitación ni fraude.

        Los 480 SKU huérfanos ocupan un bloque contiguo que arranca justo
        encima del máximo catalogado. Un error de digitación produciría
        dispersión aleatoria dentro del rango válido.
        """
        catalogo = set(datos_crudos["inventario"]["SKU_ID"])
        vendidos = set(datos_crudos["transacciones"]["SKU_ID"])
        huerfanos = vendidos - catalogo
        assert len(huerfanos) == 480
        assert max(catalogo) == "PROD-3499"
        assert min(huerfanos) == "PROD-3500"
        assert all(sku > max(catalogo) for sku in huerfanos)

    def test_feedback_sin_transacciones_huerfanas(self, datos_crudos):
        """El vínculo feedback->venta sí es íntegro; el roto es SKU->inventario."""
        trx_ids = set(datos_crudos["transacciones"]["Transaccion_ID"])
        assert datos_crudos["feedback"]["Transaccion_ID"].isin(trx_ids).all()

    def test_centinela_999_en_tiempo_entrega(self, datos_crudos):
        """999 es un código de error del sistema, no una entrega lenta real."""
        tiempos = pd.to_numeric(
            datos_crudos["transacciones"]["Tiempo_Entrega_Real"], errors="coerce"
        )
        extremos = tiempos[tiempos > 100]
        assert extremos.nunique() == 1 and extremos.iloc[0] == 999
        assert len(extremos) == 50

    def test_costos_atipicos_aislados(self, datos_crudos):
        """Solo dos costos son implausibles; el resto vive en [50, 1500]."""
        costos = pd.to_numeric(
            datos_crudos["inventario"]["Costo_Unitario_USD"], errors="coerce"
        )
        assert (costos < 1).sum() == 1
        assert (costos > 100_000).sum() == 1
        centrales = costos[(costos >= 1) & (costos <= 100_000)]
        assert centrales.min() >= 50 and centrales.max() <= 1_500


class TestSupuestosDeNegocio:
    """Supuestos que, de romperse, invalidan las respuestas a las 5 preguntas."""

    def test_nps_es_ruido_no_correlacionado(self, datos_crudos):
        """Hallazgo crítico: Satisfaccion_NPS no correlaciona con nada.

        Si esta prueba empezara a fallar significaría que el dato sí porta
        señal y que la pregunta 2 puede responderse por correlación directa.
        """
        fbk = datos_crudos["feedback"].copy()
        for col in ("Rating_Producto", "Rating_Logistica", "Satisfaccion_NPS"):
            fbk[col] = pd.to_numeric(fbk[col], errors="coerce")
        validos = fbk[fbk["Rating_Producto"].between(*config.RANGO_RATING)]

        rho = validos[["Rating_Producto", "Rating_Logistica",
                       "Satisfaccion_NPS"]].corr(method="spearman")
        assert abs(rho.loc["Rating_Producto", "Satisfaccion_NPS"]) < 0.05
        assert abs(rho.loc["Rating_Logistica", "Satisfaccion_NPS"]) < 0.05

    def test_nps_sigue_distribucion_uniforme(self, datos_crudos):
        """NPS ~ Uniforme(-100, 100): media~0, sigma~57.7, cuartiles ~+-50."""
        nps = pd.to_numeric(
            datos_crudos["feedback"]["Satisfaccion_NPS"], errors="coerce"
        )
        assert abs(nps.mean()) < 5
        assert abs(nps.std() - 57.7) < 3
        assert abs(nps.quantile(0.25) + 50) < 5
        assert abs(nps.quantile(0.75) - 50) < 5
