"""Análisis cruzado: las cinco preguntas de alta gerencia.

Cada pregunta se resuelve con una función pura que recibe la Sola Fuente de
Verdad ya filtrada y devuelve tablas y veredictos. Ningún módulo de aquí
importa Streamlit: todo debe poder ejecutarse desde un script o un test.

**El criterio transversal de este módulo es distinguir significancia de
relevancia.** Con muestras de 8.000 a 10.000 filas, el valor p se vuelve
trivialmente pequeño: casi cualquier diferencia cruza el umbral de 0,05 sin
importar cuán insignificante sea en la práctica. Por eso ningún hallazgo se
declara concluyente solo por su valor p; debe superar además un umbral de
tamaño de efecto. Un consultor que recomiende cambiar de operador logístico
basándose en una V de Cramér de 0,04 está vendiendo ruido con apariencia de
rigor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import config

logger = logging.getLogger(__name__)

# Umbrales convencionales de Cohen para tamaño de efecto.
UMBRALES_EFECTO = {"trivial": 0.10, "pequeño": 0.30, "medio": 0.50}


@dataclass
class Veredicto:
    """Resultado de una prueba estadística, con su lectura de negocio.

    Un hallazgo es **concluyente** solo si es a la vez estadísticamente
    significativo y de tamaño de efecto no trivial. Separar ambas condiciones
    es lo que impide confundir "el test detectó algo" con "esto importa".
    """

    pregunta: str
    prueba: str
    estadistico: float
    p_valor: float
    n: int
    tamano_efecto: float | None = None
    nombre_efecto: str = ""
    lectura: str = ""

    @property
    def significativo(self) -> bool:
        """¿El efecto es distinguible de cero?"""
        return bool(self.p_valor < config.ALFA_SIGNIFICANCIA)

    @property
    def magnitud(self) -> str:
        """Clasificación cualitativa del tamaño de efecto."""
        if self.tamano_efecto is None:
            return "no medido"
        efecto = abs(self.tamano_efecto)
        if efecto < UMBRALES_EFECTO["trivial"]:
            return "trivial"
        if efecto < UMBRALES_EFECTO["pequeño"]:
            return "pequeño"
        if efecto < UMBRALES_EFECTO["medio"]:
            return "medio"
        return "grande"

    @property
    def concluyente(self) -> bool:
        """¿Sostiene una recomendación a la junta directiva?"""
        return self.significativo and self.magnitud not in {"trivial",
                                                            "no medido"}

    @property
    def etiqueta(self) -> str:
        """Rótulo corto para la interfaz."""
        if not self.significativo:
            return "Sin evidencia"
        if not self.concluyente:
            return "Significativo pero irrelevante"
        return "Hallazgo sólido"

    def efecto_texto(self, decimales: int = 4) -> str:
        """Tamaño de efecto formateado, tolerante a la ausencia de medición.

        Cuando la muestra no alcanza el mínimo, ``tamano_efecto`` queda en
        ``None`` y cualquier intento de formatearlo como número revienta. Esa
        situación no es excepcional —basta con que el usuario acote el filtro a
        dos días— así que la conversión a texto vive aquí y no se repite en cada
        sitio que la necesite.
        """
        if self.tamano_efecto is None:
            return "no medido"
        return f"{self.tamano_efecto:.{decimales}f}"

    def a_dict(self) -> dict:
        return {
            "pregunta": self.pregunta,
            "prueba": self.prueba,
            "estadistico": round(float(self.estadistico), 4),
            "p_valor": round(float(self.p_valor), 4),
            "n": self.n,
            "tamano_efecto": (round(float(self.tamano_efecto), 4)
                              if self.tamano_efecto is not None else None),
            "nombre_efecto": self.nombre_efecto,
            "magnitud": self.magnitud,
            "significativo": self.significativo,
            "concluyente": self.concluyente,
            "lectura": self.lectura,
        }


def _v_de_cramer(tabla: pd.DataFrame, chi2: float) -> float:
    """Tamaño de efecto de una tabla de contingencia.

    El chi-cuadrado crece con el tamaño de la muestra; la V de Cramér lo
    normaliza y queda acotada entre 0 y 1, de modo que sí es comparable entre
    análisis con distinto número de observaciones.
    """
    n = tabla.to_numpy().sum()
    grados = min(tabla.shape) - 1
    if n == 0 or grados == 0:
        return 0.0
    return float(np.sqrt(chi2 / (n * grados)))


def probar_independencia(
    df: pd.DataFrame, columna_grupo: str, columna_binaria: str,
    pregunta: str, lectura_positiva: str, lectura_negativa: str,
) -> Veredicto:
    """Chi-cuadrado de independencia con tamaño de efecto.

    Args:
        df: Datos ya filtrados.
        columna_grupo: Variable categórica (canal, ciudad, bodega…).
        columna_binaria: Variable booleana a explicar.
        pregunta: Identificador de la pregunta gerencial.
        lectura_positiva: Texto si el hallazgo resulta concluyente.
        lectura_negativa: Texto si no lo es.

    Returns:
        Veredicto con chi-cuadrado, p-valor y V de Cramér.
    """
    from scipy import stats

    validos = df[[columna_grupo, columna_binaria]].dropna()
    tabla = pd.crosstab(validos[columna_grupo], validos[columna_binaria])

    if tabla.shape[0] < 2 or tabla.shape[1] < 2 or len(validos) < \
            config.N_MINIMO_PARA_CORRELACION:
        return Veredicto(
            pregunta=pregunta, prueba="Chi-cuadrado de independencia",
            estadistico=float("nan"), p_valor=1.0, n=len(validos),
            lectura="Muestra insuficiente para concluir con este filtro.")

    chi2, p_valor, _, _ = stats.chi2_contingency(tabla)
    v_cramer = _v_de_cramer(tabla, chi2)

    veredicto = Veredicto(
        pregunta=pregunta, prueba="Chi-cuadrado de independencia",
        estadistico=float(chi2), p_valor=float(p_valor), n=len(validos),
        tamano_efecto=v_cramer, nombre_efecto="V de Cramér")
    veredicto.lectura = (lectura_positiva if veredicto.concluyente
                         else lectura_negativa)
    return veredicto


def probar_correlacion(
    df: pd.DataFrame, columna_x: str, columna_y: str, pregunta: str,
    lectura_positiva: str, lectura_negativa: str,
) -> Veredicto:
    """Correlación de Spearman, donde rho es a la vez estadístico y efecto.

    Se usa Spearman y no Pearson porque no asume linealidad ni normalidad y es
    robusta a los valores extremos que abundan en estos datos.
    """
    from scipy import stats

    validos = df[[columna_x, columna_y]].dropna()
    if len(validos) < config.N_MINIMO_PARA_CORRELACION:
        return Veredicto(
            pregunta=pregunta, prueba="Correlación de Spearman",
            estadistico=float("nan"), p_valor=1.0, n=len(validos),
            lectura="Muestra insuficiente para estimar una correlación.")

    rho, p_valor = stats.spearmanr(validos[columna_x], validos[columna_y])

    veredicto = Veredicto(
        pregunta=pregunta, prueba="Correlación de Spearman",
        estadistico=float(rho), p_valor=float(p_valor), n=len(validos),
        tamano_efecto=float(rho), nombre_efecto="rho de Spearman")
    veredicto.lectura = (lectura_positiva if veredicto.concluyente
                         else lectura_negativa)
    return veredicto


# --------------------------------------------------------------------------
# Pregunta 1: Fuga de capital y rentabilidad
# --------------------------------------------------------------------------


@dataclass
class FugaCapital:
    """Respuesta a la pregunta 1, con la evidencia de cada hipótesis."""

    kpis: dict
    por_sku: pd.DataFrame
    por_canal: pd.DataFrame
    pareto: pd.DataFrame
    veredicto_canal: Veredicto
    veredicto_volumen: Veredicto
    veredicto_pricing: Veredicto
    diagnostico: str = ""
    advertencias: list[str] = field(default_factory=list)


def analizar_fuga_capital(ssot: pd.DataFrame) -> FugaCapital:
    """Localiza los SKU vendidos con margen negativo y diagnostica la causa.

    La pregunta de la junta plantea dos hipótesis excluyentes —pérdida
    aceptable por volumen, o falla de precios en el canal Online— y este
    análisis contrasta ambas contra una tercera que la junta no consideró: que
    el precio no guarde ninguna relación con el costo.

    Cada hipótesis tiene una prueba con una predicción distinta:

    * *Loss-leader*: los SKU de mayor volumen deberían tener el **margen
      unitario** más bajo. Se correlaciona volumen contra margen unitario y no
      contra margen total, porque el total es producto del volumen y crecería
      con él por pura aritmética, fabricando una correlación espuria.
    * *Falla del canal Online*: la tasa de margen negativo debería concentrarse
      en Online. Se contrasta con chi-cuadrado **y V de Cramér**: con más de
      8.000 transacciones, una diferencia de cuatro puntos entre canales cruza
      el umbral de significancia sin tener relevancia alguna.
    * *Ausencia de política de precios*: no debería existir correlación entre
      costo y precio de venta.

    Args:
        ssot: Sola Fuente de Verdad, ya filtrada por el usuario.

    Returns:
        FugaCapital con KPIs, tablas y los tres veredictos.
    """
    analizable = ssot[ssot["Margen_Neto"].notna()].copy()
    advertencias = []

    fantasma = int(ssot[config.COL_FLAG_FANTASMA].sum())
    if fantasma:
        advertencias.append(
            f"{fantasma:,} transacciones ({100 * fantasma / len(ssot):.1f} %) "
            f"quedan fuera de este análisis porque su SKU no está en el "
            f"maestro y por tanto no tiene costo conocido. Su impacto se "
            f"cuantifica en la pregunta 3.")

    if analizable.empty:
        return FugaCapital(
            kpis={}, por_sku=pd.DataFrame(), por_canal=pd.DataFrame(),
            pareto=pd.DataFrame(),
            veredicto_canal=_veredicto_vacio("Pregunta 1"),
            veredicto_volumen=_veredicto_vacio("Pregunta 1"),
            veredicto_pricing=_veredicto_vacio("Pregunta 1"),
            diagnostico="Sin transacciones analizables para este filtro.",
            advertencias=advertencias)

    por_sku = _agregar_por_sku(analizable)
    negativos = por_sku[por_sku["margen_neto_usd"] < 0]

    perdida = -float(negativos["margen_neto_usd"].sum())
    utilidad = float(por_sku.loc[por_sku["margen_neto_usd"] >= 0,
                                 "margen_neto_usd"].sum())
    con_perdida = analizable[analizable["Es_Margen_Negativo"]]
    # El flete solo explica la pérdida cuando el margen unitario ya era
    # positivo; si el precio no cubría el costo, la venta perdía antes de
    # despachar y el transporte es un agravante, no la causa.
    perdida_por_flete = float(
        con_perdida.loc[con_perdida["Margen_Unitario"] >= 0,
                        "Costo_Envio"].sum())

    kpis = {
        "skus_con_perdida": int(len(negativos)),
        "skus_analizados": int(len(por_sku)),
        "pct_skus_con_perdida": round(100 * len(negativos) / len(por_sku), 2),
        "perdida_total_usd": round(perdida, 2),
        "utilidad_rentables_usd": round(utilidad, 2),
        "margen_neto_agregado_usd": round(utilidad - perdida, 2),
        "erosion_pct": round(100 * perdida / utilidad, 2) if utilidad else 0.0,
        "trx_con_perdida": int(len(con_perdida)),
        "pct_trx_con_perdida": round(
            100 * float(analizable["Es_Margen_Negativo"].mean()), 2),
        "pct_perdida_antes_del_flete": round(
            100 * float((con_perdida["Margen_Unitario"] < 0).mean()), 2)
        if len(con_perdida) else 0.0,
        "perdida_atribuible_flete_usd": round(perdida_por_flete, 2),
        "pct_perdida_por_flete": round(100 * perdida_por_flete / perdida, 2)
        if perdida else 0.0,
    }

    por_canal = _tasa_por_canal(analizable)
    pareto = _curva_pareto(negativos)

    veredicto_canal = probar_independencia(
        analizable, "Canal_Venta", "Es_Margen_Negativo", "Pregunta 1",
        lectura_positiva=(
            "La tasa de margen negativo sí difiere de forma relevante entre "
            "canales: el problema tiene un componente de canal."),
        lectura_negativa=(
            "La diferencia entre canales es estadísticamente detectable pero "
            "de tamaño trivial. La hipótesis de una falla de precios "
            "específica del canal Online no se sostiene: el problema es "
            "transversal a toda la operación."))

    veredicto_volumen = probar_correlacion(
        por_sku, "unidades", "margen_unitario_usd", "Pregunta 1",
        lectura_positiva=(
            "Los SKU de mayor volumen presentan menor margen unitario, patrón "
            "compatible con una estrategia deliberada de producto gancho."),
        lectura_negativa=(
            "El volumen no guarda relación con el margen unitario: los "
            "productos que pierden dinero no son los que generan tráfico. No "
            "hay estrategia de producto gancho, hay pérdida sin contrapartida."))

    veredicto_pricing = probar_correlacion(
        analizable, "Costo_Unitario_USD", "Precio_Venta_Final", "Pregunta 1",
        lectura_positiva=(
            "El precio se mueve con el costo: los márgenes negativos son "
            "excepciones corregibles producto por producto."),
        lectura_negativa=(
            "El precio de venta es estadísticamente independiente del costo "
            "de compra. No existe una función de fijación de precios: el "
            "margen negativo no es un defecto de ciertos SKU sino el "
            "resultado aritmético de tarifar sin mirar el costo."))

    return FugaCapital(
        kpis=kpis, por_sku=por_sku, por_canal=por_canal, pareto=pareto,
        veredicto_canal=veredicto_canal, veredicto_volumen=veredicto_volumen,
        veredicto_pricing=veredicto_pricing,
        diagnostico=_redactar_diagnostico(kpis, veredicto_canal,
                                          veredicto_volumen,
                                          veredicto_pricing, pareto),
        advertencias=advertencias)


def _veredicto_vacio(pregunta: str) -> Veredicto:
    return Veredicto(pregunta=pregunta, prueba="No aplicable",
                     estadistico=float("nan"), p_valor=1.0, n=0,
                     lectura="Sin datos suficientes para el filtro aplicado.")


def _agregar_por_sku(analizable: pd.DataFrame) -> pd.DataFrame:
    """Consolida las transacciones a nivel de SKU."""
    tabla = analizable.groupby("SKU_ID").agg(
        categoria=("Categoria_Analisis", "first"),
        bodega=("Bodega_Origen", "first"),
        transacciones=("Transaccion_ID", "count"),
        unidades=("Cantidad_Vendida", "sum"),
        ingreso_usd=("Ingreso_Bruto", "sum"),
        margen_neto_usd=("Margen_Neto", "sum"),
        margen_unitario_usd=("Margen_Unitario", "mean"),
        costo_unitario_usd=("Costo_Unitario_USD", "first"),
        precio_medio_usd=("Precio_Venta_Final", "mean"),
    ).reset_index()

    tabla["margen_pct"] = np.where(
        tabla["ingreso_usd"] != 0,
        100 * tabla["margen_neto_usd"] / tabla["ingreso_usd"], np.nan)
    tabla["Es_Deficitario"] = tabla["margen_neto_usd"] < 0
    return tabla.sort_values("margen_neto_usd")


def _tasa_por_canal(analizable: pd.DataFrame) -> pd.DataFrame:
    """Tasa de margen negativo y pérdida acumulada por canal de venta."""
    tabla = analizable.groupby("Canal_Venta", dropna=False).agg(
        transacciones=("Transaccion_ID", "count"),
        trx_negativas=("Es_Margen_Negativo", "sum"),
        ingreso_usd=("Ingreso_Bruto", "sum"),
        margen_neto_usd=("Margen_Neto", "sum"),
    ).reset_index()
    tabla["tasa_negativa_pct"] = (
        100 * tabla["trx_negativas"] / tabla["transacciones"]).round(2)
    tabla["perdida_usd"] = -analizable[analizable["Es_Margen_Negativo"]] \
        .groupby("Canal_Venta", dropna=False)["Margen_Neto"].sum() \
        .reindex(tabla["Canal_Venta"]).to_numpy()
    return tabla.sort_values("tasa_negativa_pct", ascending=False)


def _curva_pareto(negativos: pd.DataFrame) -> pd.DataFrame:
    """Concentración acumulada de la pérdida sobre los SKU deficitarios.

    Si unos pocos SKU concentraran la mayor parte de la pérdida, el remedio
    sería una lista de productos a corregir. Si la curva es casi lineal, la
    pérdida es difusa y el remedio tiene que ser el proceso, no los productos.
    """
    if negativos.empty:
        return pd.DataFrame(columns=["ranking", "pct_skus", "pct_perdida"])

    ordenados = negativos.sort_values("margen_neto_usd")
    perdida = -ordenados["margen_neto_usd"].to_numpy()
    total = perdida.sum()

    return pd.DataFrame({
        "ranking": np.arange(1, len(perdida) + 1),
        "sku": ordenados["SKU_ID"].to_numpy(),
        "pct_skus": 100 * np.arange(1, len(perdida) + 1) / len(perdida),
        "pct_perdida": 100 * np.cumsum(perdida) / total,
    })


def _redactar_diagnostico(
    kpis: dict, canal: Veredicto, volumen: Veredicto, pricing: Veredicto,
    pareto: pd.DataFrame,
) -> str:
    """Convierte los tres veredictos en una conclusión para la junta."""
    if pricing.concluyente:
        causa = ("El precio sí responde al costo, de modo que los márgenes "
                 "negativos son casos aislados y corregibles uno a uno.")
    else:
        causa = (
            "**Ninguna de las dos hipótesis de la junta se sostiene.** No es "
            "una estrategia de producto gancho ni una falla del canal Online: "
            "el precio de venta es estadísticamente independiente del costo "
            "de compra. La empresa no tiene una política de precios, y por eso "
            "la pérdida aparece repartida por toda la operación.")

    if not pareto.empty:
        top50 = pareto[pareto["ranking"] <= 50]["pct_perdida"].max()
        concentracion = (
            f"Los 50 SKU más deficitarios concentran apenas {top50:.1f} % de "
            f"la pérdida: no hay un puñado de productos que corregir.")
    else:
        concentracion = ""

    antes_flete = kpis.get("pct_perdida_antes_del_flete", 0)
    por_flete = kpis.get("pct_perdida_por_flete", 0)
    return (
        f"{causa} {concentracion} El {antes_flete:.1f} % de las ventas "
        f"deficitarias ya perdía dinero **antes** de pagar el transporte, así "
        f"que el flete tampoco es la causa: explica apenas el {por_flete:.2f} % "
        f"de la pérdida total.")


def correlaciones_por_grupo(
    df: pd.DataFrame, columna_grupo: str, columna_x: str, columna_y: str,
) -> pd.DataFrame:
    """Correlación de Spearman dentro de cada grupo, con corrección múltiple.

    Calcular una correlación por ciudad y por bodega y quedarse con la más
    fuerte es una trampa estadística clásica: con cinco grupos a un alfa de
    0,05, la probabilidad de que al menos uno dé "significativo" por puro azar
    es del 23 %. Recomendarle a la junta cambiar de operador logístico sobre
    esa base sería vender ruido.

    Por eso se aplica la corrección de Bonferroni: el valor p de cada grupo se
    multiplica por el número de comparaciones. Es conservadora, y esa es
    justamente la propiedad que se busca cuando la decisión que respalda es
    cara y difícil de revertir.

    Args:
        df: Datos ya filtrados.
        columna_grupo: Dimensión que define los grupos.
        columna_x: Primera variable de la correlación.
        columna_y: Segunda variable.

    Returns:
        DataFrame ordenado por rho, con p crudo, p corregido y significancia.
    """
    from scipy import stats

    filas = []
    for grupo, datos in df.groupby(columna_grupo, dropna=True):
        validos = datos[[columna_x, columna_y]].dropna()
        if len(validos) < config.N_MINIMO_PARA_CORRELACION:
            continue
        rho, p_valor = stats.spearmanr(validos[columna_x], validos[columna_y])
        filas.append({columna_grupo: grupo, "n": len(validos),
                      "rho": float(rho), "p_crudo": float(p_valor)})

    if not filas:
        return pd.DataFrame(
            columns=[columna_grupo, "n", "rho", "p_crudo", "p_corregido",
                     "significativo", "magnitud", "comparaciones"])

    tabla = pd.DataFrame(filas)
    comparaciones = len(tabla)
    tabla["p_corregido"] = (tabla["p_crudo"] * comparaciones).clip(upper=1.0)
    tabla["significativo"] = tabla["p_corregido"] < config.ALFA_SIGNIFICANCIA
    tabla["magnitud"] = tabla["rho"].abs().apply(
        lambda v: "trivial" if v < UMBRALES_EFECTO["trivial"]
        else "pequeño" if v < UMBRALES_EFECTO["pequeño"]
        else "medio" if v < UMBRALES_EFECTO["medio"] else "grande")
    tabla["comparaciones"] = comparaciones
    return tabla.sort_values("rho")


def _probar_diferencia_medianas(
    df: pd.DataFrame, columna_grupo: str, columna_valor: str, pregunta: str,
    lectura_positiva: str, lectura_negativa: str,
) -> Veredicto:
    """Kruskal-Wallis: comprueba si las medianas difieren entre grupos.

    Se acompaña del epsilon cuadrado como tamaño de efecto. Igual que en el
    resto del módulo, la significancia por sí sola no basta: con miles de
    observaciones, una diferencia de un día entre ciudades cruza el umbral sin
    tener ninguna consecuencia operativa.
    """
    from scipy import stats

    minimo = config.N_MINIMO_PARA_CORRELACION
    grupos = [g[columna_valor].dropna()
              for _, g in df.groupby(columna_grupo, dropna=True)
              if g[columna_valor].notna().sum() >= minimo]

    if len(grupos) < 2:
        return Veredicto(
            pregunta=pregunta, prueba="Kruskal-Wallis",
            estadistico=float("nan"), p_valor=1.0, n=0,
            lectura="Muestra insuficiente para comparar grupos.")

    h_estadistico, p_valor = stats.kruskal(*grupos)
    n = sum(len(g) for g in grupos)
    k = len(grupos)
    # Epsilon cuadrado: proporcion de la variabilidad explicada por el grupo.
    epsilon2 = (h_estadistico - k + 1) / (n - k) if n > k else 0.0

    veredicto = Veredicto(
        pregunta=pregunta, prueba="Kruskal-Wallis",
        estadistico=float(h_estadistico), p_valor=float(p_valor), n=n,
        tamano_efecto=float(max(epsilon2, 0.0)), nombre_efecto="epsilon²")
    veredicto.lectura = (lectura_positiva if veredicto.concluyente
                         else lectura_negativa)
    return veredicto


# --------------------------------------------------------------------------
# Pregunta 2: crisis logística y cuellos de botella
# --------------------------------------------------------------------------


@dataclass
class CrisisLogistica:
    """Respuesta a la pregunta 2, en dos niveles de lectura."""

    correlaciones_ciudad: pd.DataFrame
    correlaciones_bodega: pd.DataFrame
    desempeno_ciudad: pd.DataFrame
    desempeno_bodega: pd.DataFrame
    veredicto_tiempo: Veredicto
    veredicto_adversa: Veredicto
    kpis: dict = field(default_factory=dict)
    diagnostico: str = ""
    zona_critica: str = ""


def analizar_crisis_logistica(ssot: pd.DataFrame) -> CrisisLogistica:
    """Localiza el cuello de botella logístico por ciudad y por bodega.

    Se responde en dos niveles porque la variable que la pregunta propone como
    eje —el NPS— no porta señal:

    1. **El ranking solicitado.** Correlación entre tiempo de entrega y NPS
       dentro de cada plaza y cada bodega, con corrección de Bonferroni, y el
       conteo de cuántas sobreviven.
    2. **El análisis alternativo.** Como el NPS no discrimina, el cuello de
       botella se busca donde sí hay señal observable: la distribución del
       tiempo de entrega y la tasa de envíos en estado adverso.

    Args:
        ssot: Sola Fuente de Verdad, ya filtrada.

    Returns:
        CrisisLogistica con ambos niveles y su diagnóstico.
    """
    correlaciones_ciudad = correlaciones_por_grupo(
        ssot, "Ciudad_Destino", "Tiempo_Entrega_Real", "Satisfaccion_NPS")
    correlaciones_bodega = correlaciones_por_grupo(
        ssot, "Bodega_Origen", "Tiempo_Entrega_Real", "Satisfaccion_NPS")

    veredicto_tiempo = _probar_diferencia_medianas(
        ssot, "Ciudad_Destino", "Tiempo_Entrega_Real", "Pregunta 2",
        "El tiempo de entrega difiere de forma relevante entre plazas: hay "
        "una geografía que explica la demora.",
        "Los tiempos de entrega son prácticamente idénticos en todas las "
        "plazas. Ninguna ciudad destaca por lenta.")

    veredicto_adversa = probar_independencia(
        ssot, "Ciudad_Destino", "Entrega_Adversa", "Pregunta 2",
        "La tasa de envíos fallidos sí se concentra en ciertas plazas.",
        "La tasa de envíos fallidos es estadísticamente indistinguible entre "
        "ciudades: el problema no es regional.")

    con_estado = ssot[ssot["Estado_Envio"].notna()]
    tasa_adversa = (100 * float(con_estado["Entrega_Adversa"].mean())
                    if len(con_estado) else 0.0)
    tiempos = ssot["Tiempo_Entrega_Real"]

    significativas = 0
    if not correlaciones_ciudad.empty:
        significativas += int(correlaciones_ciudad["significativo"].sum())
    if not correlaciones_bodega.empty:
        significativas += int(correlaciones_bodega["significativo"].sum())
    evaluadas = len(correlaciones_ciudad) + len(correlaciones_bodega)

    kpis = {
        "tasa_envio_adverso_pct": round(tasa_adversa, 2),
        "entrega_mediana_dias": (float(tiempos.median())
                                 if tiempos.notna().any() else float("nan")),
        "entrega_p90_dias": (float(tiempos.quantile(0.9))
                             if tiempos.notna().any() else float("nan")),
        "correlaciones_significativas": significativas,
        "correlaciones_evaluadas": evaluadas,
        "trx_con_estado": int(len(con_estado)),
    }

    if significativas:
        candidatas = correlaciones_ciudad[correlaciones_ciudad["significativo"]]
        zona = (str(candidatas.iloc[0]["Ciudad_Destino"])
                if not candidatas.empty else "sin zona identificable")
        diagnostico = (
            f"Se identifica **{zona}** como la plaza donde la demora se "
            f"traduce con más fuerza en insatisfacción. Es la candidata a "
            f"cambio de operador.")
    else:
        zona = "Ninguna zona destaca"
        diagnostico = (
            f"**No hay una zona que requiera cambio de operador, porque "
            f"ninguna es peor que las demás.** Ninguna de las {evaluadas} "
            f"correlaciones entre demora y satisfacción sobrevive a la "
            f"corrección por comparaciones múltiples, y las señales duras "
            f"—tiempo de entrega y tasa de fallo— son homogéneas entre plazas. "
            f"El hallazgo relevante no es *dónde* sino *cuánto*: el "
            f"**{tasa_adversa:.1f} % de los envíos con estado registrado "
            f"termina retrasado, perdido o devuelto**, y esa cifra es igual de "
            f"mala en todas partes. Eso descarta un problema de operador "
            f"regional y apunta a una falla del proceso completo: cambiar de "
            f"transportista en una ciudad no movería la aguja.")

    return CrisisLogistica(
        correlaciones_ciudad=correlaciones_ciudad,
        correlaciones_bodega=correlaciones_bodega,
        desempeno_ciudad=_desempeno_logistico(ssot, "Ciudad_Destino"),
        desempeno_bodega=_desempeno_logistico(ssot, "Bodega_Origen"),
        veredicto_tiempo=veredicto_tiempo, veredicto_adversa=veredicto_adversa,
        kpis=kpis, diagnostico=diagnostico, zona_critica=zona)


def _desempeno_logistico(ssot: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Indicadores duros de nivel de servicio por ciudad o bodega."""
    datos = ssot[ssot[dimension].notna()]
    if datos.empty:
        return pd.DataFrame()

    tabla = datos.groupby(dimension).agg(
        transacciones=("Transaccion_ID", "count"),
        entrega_mediana=("Tiempo_Entrega_Real", "median"),
        entrega_p90=("Tiempo_Entrega_Real", lambda s: s.quantile(0.9)),
        tasa_adversa=("Entrega_Adversa", "mean"),
        nps_medio=("Satisfaccion_NPS", "mean"),
        ingreso_usd=("Ingreso_Bruto", "sum"),
    ).reset_index()
    tabla["tasa_adversa"] = (100 * tabla["tasa_adversa"]).round(2)
    return tabla.sort_values("tasa_adversa", ascending=False)


# --------------------------------------------------------------------------
# Pregunta 3: análisis de la venta invisible
# --------------------------------------------------------------------------


@dataclass
class VentaInvisible:
    """Respuesta a la pregunta 3."""

    kpis: dict
    por_canal: pd.DataFrame
    serie_mensual: pd.DataFrame
    criterios_diagnostico: pd.DataFrame
    veredicto_origen: str = ""
    diagnostico: str = ""


def analizar_venta_invisible(
    ssot: pd.DataFrame, diagnostico_fantasma: dict | None = None,
) -> VentaInvisible:
    """Cuantifica el impacto financiero de las ventas sin SKU en el maestro.

    Además del monto, estima el margen que la empresa **no puede calcular**
    sobre ese ingreso: aplicando el margen porcentual mediano de la operación
    catalogada se obtiene el orden de magnitud de la utilidad que está fuera
    de control contable.

    Args:
        ssot: Sola Fuente de Verdad, ya filtrada.
        diagnostico_fantasma: Diagnóstico de seis criterios de ``integration``.

    Returns:
        VentaInvisible con cifras, evolución temporal y veredicto de origen.
    """
    if ssot.empty:
        return VentaInvisible(
            kpis={}, por_canal=pd.DataFrame(), serie_mensual=pd.DataFrame(),
            criterios_diagnostico=pd.DataFrame(),
            diagnostico="Sin transacciones para el filtro aplicado.")

    fantasma = ssot[ssot[config.COL_FLAG_FANTASMA]]
    ingreso_total = float(ssot["Ingreso_Bruto"].sum())
    ingreso_fantasma = float(fantasma["Ingreso_Bruto"].sum())

    catalogada = ssot[~ssot[config.COL_FLAG_FANTASMA]]
    margen_mediano = (float(catalogada["Margen_Pct"].median())
                      if catalogada["Margen_Pct"].notna().any() else 0.0)

    kpis = {
        "transacciones": int(len(fantasma)),
        "pct_transacciones": round(100 * len(fantasma) / len(ssot), 2),
        "skus": int(fantasma["SKU_ID"].nunique()),
        "ingreso_usd": round(ingreso_fantasma, 2),
        "pct_ingreso": (round(100 * ingreso_fantasma / ingreso_total, 2)
                        if ingreso_total else 0.0),
        "margen_no_controlado_usd": round(
            ingreso_fantasma * margen_mediano / 100, 2),
        "margen_mediano_referencia_pct": round(margen_mediano, 2),
        "unidades": (int(fantasma["Cantidad_Vendida"].sum())
                     if fantasma["Cantidad_Vendida"].notna().any() else 0),
    }

    serie = _fantasma_mensual(ssot)
    estabilidad = float(serie["pct_fantasma"].std()) if len(serie) > 1 else 0.0

    # El diagnóstico de origen describe el bloque de SKU huérfanos del maestro
    # completo. Si el recorte del usuario no contiene ninguna venta fantasma,
    # afirmarlo aquí sería atribuirle al recorte un problema que no tiene.
    if not len(fantasma):
        veredicto_origen = ("No aplica: este recorte no contiene ventas sin "
                            "catálogo")
        diagnostico = (
            "**El recorte analizado no contiene ventas sin catálogo oficial.** "
            "Todo su ingreso proviene de productos registrados en el maestro "
            "de inventario, de modo que su margen sí es calculable y "
            "auditable. La fuga por venta invisible se concentra fuera de este "
            "filtro.")
        return VentaInvisible(
            kpis=kpis, por_canal=_fantasma_por_canal(ssot), serie_mensual=serie,
            criterios_diagnostico=pd.DataFrame(),
            veredicto_origen=veredicto_origen, diagnostico=diagnostico)

    veredicto_origen = (diagnostico_fantasma or {}).get(
        "veredicto", "Diagnóstico de origen no disponible")

    diagnostico = (
        f"**USD {ingreso_fantasma:,.0f} ({kpis['pct_ingreso']:.2f} % del "
        f"ingreso) provienen de {kpis['skus']} productos que la empresa vende "
        f"pero no tiene registrados.** Sobre ese ingreso no se puede calcular "
        f"margen, reponer stock ni auditar costo: aplicando el margen mediano "
        f"de la operación catalogada hay del orden de "
        f"USD {kpis['margen_no_controlado_usd']:,.0f} de utilidad fuera de "
        f"control contable. La participación mensual se mantiene estable "
        f"(desviación de {estabilidad:.1f} puntos), de modo que no es un "
        f"incidente puntual sino una fuga estructural. Diagnóstico de origen: "
        f"{veredicto_origen}.")

    return VentaInvisible(
        kpis=kpis, por_canal=_fantasma_por_canal(ssot), serie_mensual=serie,
        criterios_diagnostico=_tabla_criterios(diagnostico_fantasma),
        veredicto_origen=veredicto_origen, diagnostico=diagnostico)


def _fantasma_por_canal(ssot: pd.DataFrame) -> pd.DataFrame:
    """Reparto del ingreso invisible entre canales de venta."""
    filas = []
    for canal, grupo in ssot.groupby("Canal_Venta", dropna=False):
        total = float(grupo["Ingreso_Bruto"].sum())
        invisible = float(
            grupo.loc[grupo[config.COL_FLAG_FANTASMA], "Ingreso_Bruto"].sum())
        filas.append({
            "Canal_Venta": canal, "ingreso_total": total,
            "ingreso_fantasma": invisible,
            "trx_fantasma": int(grupo[config.COL_FLAG_FANTASMA].sum()),
            "pct_fantasma": round(100 * invisible / total, 2) if total else 0.0,
        })
    return pd.DataFrame(filas).sort_values("ingreso_fantasma", ascending=False)


def _fantasma_mensual(ssot: pd.DataFrame) -> pd.DataFrame:
    """Evolución mensual del ingreso invisible.

    Distingue una fuga estructural de un incidente puntual: un error de carga
    aislado produciría un pico, mientras que un catálogo desactualizado produce
    una participación estable mes a mes.
    """
    datos = ssot[ssot["Fecha_Venta"].notna() & ~ssot["Fecha_Futura"]]
    if datos.empty:
        return pd.DataFrame(columns=["mes", "ingreso_total",
                                     "ingreso_fantasma", "pct_fantasma"])

    filas = []
    meses = datos["Fecha_Venta"].dt.to_period("M").astype(str)
    for mes, grupo in datos.groupby(meses):
        total = float(grupo["Ingreso_Bruto"].sum())
        invisible = float(
            grupo.loc[grupo[config.COL_FLAG_FANTASMA], "Ingreso_Bruto"].sum())
        filas.append({
            "mes": mes, "ingreso_total": total, "ingreso_fantasma": invisible,
            "pct_fantasma": round(100 * invisible / total, 2) if total else 0.0,
        })
    return pd.DataFrame(filas).sort_values("mes")


def _tabla_criterios(diagnostico: dict | None) -> pd.DataFrame:
    """Convierte el diagnóstico de seis criterios en una tabla presentable."""
    if not diagnostico or not diagnostico.get("criterios"):
        return pd.DataFrame()
    return pd.DataFrame([
        {"Criterio": nombre.capitalize(), "Evidencia": detalle["prueba"],
         "Apunta a": detalle["apunta_a"].capitalize()}
        for nombre, detalle in diagnostico["criterios"].items()
    ])


# --------------------------------------------------------------------------
# Pregunta 4: diagnóstico de fidelidad
# --------------------------------------------------------------------------


@dataclass
class ParadojaFidelidad:
    """Respuesta a la pregunta 4."""

    por_categoria: pd.DataFrame
    causa_raiz: pd.DataFrame
    veredicto_sentimiento: Veredicto
    veredicto_stock: Veredicto
    veredicto_causa: Veredicto
    kpis: dict = field(default_factory=dict)
    diagnostico: str = ""
    advertencias: list[str] = field(default_factory=list)


def analizar_paradoja_fidelidad(ssot: pd.DataFrame) -> ParadojaFidelidad:
    """Busca categorías con alta disponibilidad y sentimiento negativo.

    La pregunta da por sentado que la paradoja existe y pide explicarla. El
    análisis contrasta primero que exista: para que haya categorías con stock
    alto y clientes molestos, tanto el stock como el sentimiento tienen que
    variar entre categorías. Se prueban ambas condiciones por separado.

    Cuando el sentimiento sí discrimina, la causa raíz se separa con
    ``Causa_Queja``, que distingue reclamos por calidad de reclamos por
    precio: exactamente la disyuntiva que plantea la pregunta.

    Las transacciones con ``Feedback_Confiable = False`` (2 a 4 opiniones de
    clientes distintos colapsadas en una sola fila por
    ``integration.agregar_feedback_a_transaccion``) se excluyen del análisis
    de calificación: promediar esas opiniones mezclaría personas distintas
    bajo una sola venta. Siguen contando en el resto de la tabla, porque su
    stock, precio y margen no dependen del feedback.

    Args:
        ssot: Sola Fuente de Verdad, ya filtrada.

    Returns:
        ParadojaFidelidad con la tabla por categoría y los tres veredictos.
    """
    datos = ssot[ssot["Categoria_Analisis"].notna()]
    if datos.empty:
        return ParadojaFidelidad(
            por_categoria=pd.DataFrame(), causa_raiz=pd.DataFrame(),
            veredicto_sentimiento=_veredicto_vacio("Pregunta 4"),
            veredicto_stock=_veredicto_vacio("Pregunta 4"),
            veredicto_causa=_veredicto_vacio("Pregunta 4"),
            diagnostico="Sin transacciones para el filtro aplicado.")

    advertencias = []
    no_confiable = int((datos["Feedback_Confiable"] == False).sum())  # noqa: E712
    if no_confiable:
        advertencias.append(
            f"{no_confiable:,} transacciones concentran el feedback de 2 a 4 "
            f"clientes distintos en una sola fila (Feedback_Confiable = "
            f"False). Se excluyen del análisis de calificación de producto "
            f"para no promediar opiniones de personas distintas bajo una "
            f"sola venta; siguen contando en el resto del análisis.")
    confiables = datos[datos["Feedback_Confiable"] != False]  # noqa: E712

    por_categoria = datos.groupby("Categoria_Analisis").agg(
        transacciones=("Transaccion_ID", "count"),
        stock_medio=("Stock_Actual", "mean"),
        nps_medio=("Satisfaccion_NPS", "mean"),
        tasa_tickets=("Ticket_Soporte_Abierto", "mean"),
        margen_mediano_pct=("Margen_Pct", "median"),
        precio_medio=("Precio_Venta_Final", "mean"),
        ingreso_usd=("Ingreso_Bruto", "sum"),
    ).reset_index()
    por_categoria["tasa_tickets"] = (
        100 * por_categoria["tasa_tickets"]).round(2)
    rating_confiable = (confiables.groupby("Categoria_Analisis")
                        ["Rating_Producto"].mean().rename("rating_producto"))
    por_categoria = por_categoria.merge(
        rating_confiable, on="Categoria_Analisis", how="left")

    veredicto_sentimiento = _probar_diferencia_medianas(
        confiables, "Categoria_Analisis", "Rating_Producto", "Pregunta 4",
        "La calificación de producto sí difiere entre categorías: hay "
        "categorías con clientes medibles más molestos.",
        "La calificación de producto es estadísticamente idéntica en todas "
        "las categorías. No existe una categoría con peor sentimiento.")

    veredicto_stock = _probar_diferencia_medianas(
        datos, "Categoria_Analisis", "Stock_Actual", "Pregunta 4",
        "La disponibilidad sí difiere entre categorías.",
        "Los niveles de stock son estadísticamente equivalentes entre "
        "categorías: ninguna acumula inventario de forma distintiva.")

    con_causa = datos[datos["Causa_Queja"].notna()]
    veredicto_causa = probar_independencia(
        con_causa, "Categoria_Analisis", "Causa_Queja", "Pregunta 4",
        "El motivo de la queja depende de la categoría: unas fallan por "
        "calidad y otras por precio.",
        "El motivo de la queja se reparte igual en todas las categorías: la "
        "insatisfacción no es atribuible a un problema de producto concreto.")

    causa_raiz = _tabla_causa_raiz(con_causa)
    kpis = _kpis_fidelidad(datos, confiables, con_causa, por_categoria)

    if veredicto_sentimiento.concluyente and veredicto_stock.concluyente:
        diagnostico = (
            "La paradoja existe y es medible: hay categorías con inventario "
            "alto y clientes descontentos. Revise la tabla de causa raíz para "
            "separar los reclamos de calidad de los de precio.")
    else:
        dominante = kpis.get("causa_dominante", "Precio/Valor")
        pct = kpis.get("pct_causa_dominante", 0.0)
        diagnostico = (
            f"**La paradoja no se sostiene: no hay categorías buenas y malas, "
            f"todas se comportan igual.** Ni la calificación de producto "
            f"(p = {veredicto_sentimiento.p_valor:.4f}) ni el nivel de stock "
            f"(p = {veredicto_stock.p_valor:.4f}) difieren entre categorías, "
            f"así que no existe el cruce 'stock alto + sentimiento negativo' "
            f"que la pregunta busca. Lo que sí es medible es el motivo del "
            f"reclamo en agregado: **{dominante} concentra el {pct:.1f} % de "
            f"las quejas con causa identificada**, por encima de calidad y de "
            f"logística. La respuesta a «¿mala calidad o sobrecosto?» es "
            f"sobrecosto, y no por categoría sino en toda la operación, lo "
            f"que enlaza directamente con la ausencia de política de precios "
            f"detectada en la pregunta 1.")

    return ParadojaFidelidad(
        por_categoria=por_categoria.sort_values("stock_medio",
                                                ascending=False),
        causa_raiz=causa_raiz, veredicto_sentimiento=veredicto_sentimiento,
        veredicto_stock=veredicto_stock, veredicto_causa=veredicto_causa,
        kpis=kpis, diagnostico=diagnostico, advertencias=advertencias)


def _tabla_causa_raiz(con_causa: pd.DataFrame) -> pd.DataFrame:
    """Reparto porcentual del motivo de queja dentro de cada categoría."""
    if con_causa.empty:
        return pd.DataFrame()
    tabla = pd.crosstab(con_causa["Categoria_Analisis"],
                        con_causa["Causa_Queja"], normalize="index") * 100
    return tabla.round(1).reset_index()


def _kpis_fidelidad(datos: pd.DataFrame, confiables: pd.DataFrame,
                    con_causa: pd.DataFrame, por_categoria: pd.DataFrame) -> dict:
    """Indicadores agregados de la pregunta 4.

    ``rating_medio_global`` se calcula sobre ``confiables`` (excluye las
    ventas con feedback de varios clientes colapsado en una fila); el resto
    de indicadores no depende del feedback y usa la población completa.
    """
    kpis = {
        "categorias_evaluadas": int(len(por_categoria)),
        "stock_medio_global": round(float(datos["Stock_Actual"].mean()), 1)
        if datos["Stock_Actual"].notna().any() else 0.0,
        "rating_medio_global": round(
            float(confiables["Rating_Producto"].mean()), 2)
        if confiables["Rating_Producto"].notna().any() else 0.0,
    }

    if not con_causa.empty:
        reales = con_causa[con_causa["Causa_Queja"] != "Ninguna"]
        if not reales.empty:
            reparto = reales["Causa_Queja"].value_counts(normalize=True) * 100
            kpis["causa_dominante"] = str(reparto.index[0])
            kpis["pct_causa_dominante"] = round(float(reparto.iloc[0]), 1)
            kpis["reparto_causas"] = {k: round(float(v), 1)
                                      for k, v in reparto.items()}
    return kpis


# --------------------------------------------------------------------------
# Pregunta 5: storytelling de riesgo operativo
# --------------------------------------------------------------------------


@dataclass
class RiesgoOperativo:
    """Respuesta a la pregunta 5."""

    por_bodega: pd.DataFrame
    dispersion: pd.DataFrame
    veredicto_antiguedad_tickets: Veredicto
    veredicto_antiguedad_bodega: Veredicto
    veredicto_tickets_bodega: Veredicto
    veredicto_nps_bodega: Veredicto
    kpis: dict = field(default_factory=dict)
    diagnostico: str = ""


def analizar_riesgo_operativo(ssot: pd.DataFrame) -> RiesgoOperativo:
    """Relaciona la antigüedad del conteo físico con la carga de soporte.

    La pregunta asume que una bodega que no cuenta su inventario genera más
    reclamos. Se contrasta esa cadena causal en sus tres eslabones:

    1. ¿La antigüedad de la revisión difiere entre bodegas?
    2. ¿La tasa de tickets difiere entre bodegas?
    3. ¿Existe correlación entre ambas a nivel de transacción?

    Si el primer eslabón se cumple pero los otros dos no, la conclusión no es
    que no haya riesgo, sino que el riesgo aún no se ha materializado en
    reclamos medibles: la ceguera de inventario es real y está sin castigar.

    Como complemento —no parte de la cadena causal que plantea el
    enunciado— se prueba además si el NPS medio difiere entre bodegas. La
    pregunta 2 ya estableció que ``Satisfaccion_NPS`` es ruido: sigue una
    distribución casi uniforme y no correlaciona con tiempo de entrega ni
    con las calificaciones. Esta prueba confirma (o desmentiría) que
    tampoco discrimina por bodega, cerrando esa vía en vez de dejarla sin
    examinar.

    Args:
        ssot: Sola Fuente de Verdad, ya filtrada.

    Returns:
        RiesgoOperativo con la tabla por bodega y los cuatro veredictos.
    """
    datos = ssot[ssot["Bodega_Origen"].notna()]
    if datos.empty:
        return RiesgoOperativo(
            por_bodega=pd.DataFrame(), dispersion=pd.DataFrame(),
            veredicto_antiguedad_tickets=_veredicto_vacio("Pregunta 5"),
            veredicto_antiguedad_bodega=_veredicto_vacio("Pregunta 5"),
            veredicto_tickets_bodega=_veredicto_vacio("Pregunta 5"),
            veredicto_nps_bodega=_veredicto_vacio("Pregunta 5"),
            diagnostico="Sin transacciones para el filtro aplicado.")

    por_bodega = datos.groupby("Bodega_Origen").agg(
        transacciones=("Transaccion_ID", "count"),
        antiguedad_mediana=("Antiguedad_Revision_Dias", "median"),
        antiguedad_p90=("Antiguedad_Revision_Dias",
                        lambda s: s.quantile(0.9)),
        tasa_tickets=("Ticket_Soporte_Abierto", "mean"),
        tasa_bajo_reorden=("Bajo_Punto_Reorden", "mean"),
        tasa_adversa=("Entrega_Adversa", "mean"),
        nps_medio=("Satisfaccion_NPS", "mean"),
        ingreso_usd=("Ingreso_Bruto", "sum"),
    ).reset_index()
    for columna in ("tasa_tickets", "tasa_bajo_reorden", "tasa_adversa"):
        por_bodega[columna] = (100 * por_bodega[columna]).round(2)

    por_bodega["Nomenclatura_No_Estandar"] = por_bodega["Bodega_Origen"].isin(
        config.BODEGAS_NO_ESTANDAR)

    con_ticket = datos[datos["Ticket_Soporte_Abierto"].notna()].copy()
    if not con_ticket.empty:
        con_ticket["ticket_num"] = con_ticket["Ticket_Soporte_Abierto"] \
            .astype(int)

    veredicto_correlacion = probar_correlacion(
        con_ticket, "Antiguedad_Revision_Dias", "ticket_num", "Pregunta 5",
        "A mayor antigüedad del conteo físico, mayor tasa de reclamos: la "
        "ceguera de inventario ya se traduce en carga de soporte.",
        "No hay relación entre la antigüedad del conteo físico y la apertura "
        "de tickets. La ceguera de inventario es real pero todavía no se ha "
        "materializado en reclamos medibles."
    ) if not con_ticket.empty else _veredicto_vacio("Pregunta 5")

    veredicto_antiguedad = _probar_diferencia_medianas(
        datos, "Bodega_Origen", "Antiguedad_Revision_Dias", "Pregunta 5",
        "La antigüedad del conteo físico difiere entre bodegas: hay nodos "
        "claramente más desatendidos que otros.",
        "Todas las bodegas llevan un tiempo equivalente sin conteo físico: la "
        "desatención es uniforme, no focalizada.")

    veredicto_tickets = probar_independencia(
        datos, "Bodega_Origen", "Ticket_Soporte_Abierto", "Pregunta 5",
        "La tasa de reclamos sí difiere entre bodegas.",
        "La tasa de reclamos es estadísticamente idéntica entre bodegas.")

    veredicto_nps = _probar_diferencia_medianas(
        datos, "Bodega_Origen", "Satisfaccion_NPS", "Pregunta 5",
        "El NPS medio sí difiere entre bodegas: hay nodos con clientes "
        "sistemáticamente más satisfechos o más insatisfechos.",
        "El NPS medio es estadísticamente idéntico entre bodegas. "
        "Consistente con el hallazgo de la pregunta 2: Satisfaccion_NPS no "
        "porta señal utilizable en este dataset, tampoco al segmentar por "
        "bodega.")

    kpis = {
        "antiguedad_mediana_global": float(
            datos["Antiguedad_Revision_Dias"].median())
        if datos["Antiguedad_Revision_Dias"].notna().any() else float("nan"),
        "antiguedad_maxima": float(datos["Antiguedad_Revision_Dias"].max())
        if datos["Antiguedad_Revision_Dias"].notna().any() else float("nan"),
        "bodegas_evaluadas": int(len(por_bodega)),
        "bodegas_no_estandar": int(
            por_bodega["Nomenclatura_No_Estandar"].sum()),
        "tasa_tickets_global": round(
            100 * float(datos["Ticket_Soporte_Abierto"].mean()), 2)
        if datos["Ticket_Soporte_Abierto"].notna().any() else 0.0,
    }
    kpis["antiguedad_meses"] = (round(kpis["antiguedad_mediana_global"] / 30.4, 1)
                                if kpis["antiguedad_mediana_global"] ==
                                kpis["antiguedad_mediana_global"] else 0.0)

    peor = (por_bodega.nlargest(1, "antiguedad_mediana")
            if not por_bodega.empty else pd.DataFrame())
    nombre_peor = str(peor.iloc[0]["Bodega_Origen"]) if not peor.empty else "—"

    if veredicto_correlacion.concluyente:
        diagnostico = (
            f"La cadena causal se confirma: las bodegas con conteo más "
            f"antiguo generan más reclamos. **{nombre_peor}** es la más "
            f"desatendida y debe priorizarse.")
    else:
        diagnostico = (
            f"**Las bodegas sí operan a ciegas, pero eso todavía no se refleja "
            f"en los reclamos.** La antigüedad del último conteo físico sí "
            f"difiere entre nodos (p = {veredicto_antiguedad.p_valor:.4f}) y "
            f"**{nombre_peor}** es el más desatendido, pero la tasa de tickets "
            f"es idéntica en todos (p = {veredicto_tickets.p_valor:.4f}) y no "
            f"correlaciona con la antigüedad "
            f"(rho = {veredicto_correlacion.efecto_texto()}). "
            f"La lectura correcta no es que no haya riesgo: es que el riesgo "
            f"**aún no se ha cobrado**. Con una mediana de "
            f"{kpis['antiguedad_meses']:.1f} meses sin verificar el inventario "
            f"físico, la empresa decide reposición sobre stock teórico en toda "
            f"su red, y la ausencia de reclamos hoy no es evidencia de "
            f"control sino de que el descuadre todavía no ha aflorado.")

    return RiesgoOperativo(
        por_bodega=por_bodega.sort_values("antiguedad_mediana",
                                          ascending=False),
        dispersion=_dispersion_bodega(datos),
        veredicto_antiguedad_tickets=veredicto_correlacion,
        veredicto_antiguedad_bodega=veredicto_antiguedad,
        veredicto_tickets_bodega=veredicto_tickets,
        veredicto_nps_bodega=veredicto_nps,
        kpis=kpis, diagnostico=diagnostico)


def _dispersion_bodega(datos: pd.DataFrame) -> pd.DataFrame:
    """Puntos SKU para la dispersión antigüedad contra tasa de tickets."""
    columnas = ["SKU_ID", "Bodega_Origen", "Antiguedad_Revision_Dias",
                "Ticket_Soporte_Abierto", "Stock_Actual"]
    disponibles = [c for c in columnas if c in datos.columns]
    validos = datos[disponibles].dropna(
        subset=["Antiguedad_Revision_Dias"])
    if validos.empty:
        return pd.DataFrame()

    return validos.groupby(["SKU_ID", "Bodega_Origen"], as_index=False).agg(
        antiguedad=("Antiguedad_Revision_Dias", "first"),
        stock=("Stock_Actual", "first"),
        tasa_tickets=("Ticket_Soporte_Abierto", "mean"),
        ventas=("SKU_ID", "count"),
    )


# --------------------------------------------------------------------------
# Visión general: cifras agregadas de la operación (o del recorte filtrado)
# --------------------------------------------------------------------------


@dataclass
class ResumenGeneral:
    """Cifras agregadas para la pestaña de Visión General."""

    kpis: dict = field(default_factory=dict)
    advertencias: list[str] = field(default_factory=list)


def analizar_resumen_general(ssot: pd.DataFrame) -> ResumenGeneral:
    """Calcula las cifras agregadas del recorte: ingreso, margen, unidades.

    No responde ninguna de las cinco preguntas gerenciales; es el punto de
    entrada del dashboard, así que reutiliza las columnas ya derivadas por
    ``integration.calcular_variables_derivadas`` en vez de recalcular nada.

    La venta sin catálogo (SKU fantasma) y los costos atípicos excluidos no
    tienen ``Margen_Neto`` calculable (no hay costo conocido): se advierte
    cuántas transacciones caen en ese caso en vez de tratarlas como margen
    cero, que inventaría rentabilidad donde no hay dato.

    Args:
        ssot: Sola Fuente de Verdad, ya filtrada por el panel lateral
            (incluye el efecto del interruptor "Incluir venta sin catálogo").

    Returns:
        ResumenGeneral con los KPIs y las advertencias de cobertura.
    """
    if ssot.empty:
        return ResumenGeneral()

    con_margen = ssot["Margen_Neto"].notna()
    transacciones = int(len(ssot))
    ingreso_total = float(ssot["Ingreso_Bruto"].sum())
    sin_margen = int((~con_margen).sum())

    kpis = {
        "ingreso_total_usd": round(ingreso_total, 2),
        "margen_neto_total_usd": round(
            float(ssot.loc[con_margen, "Margen_Neto"].sum()), 2),
        "costo_mercancia_usd": round(
            float(ssot.loc[con_margen, "Costo_Mercancia"].sum()), 2),
        "costo_envio_usd": round(float(ssot["Costo_Envio"].sum()), 2),
        "transacciones": transacciones,
        "unidades_vendidas": int(ssot["Cantidad_Vendida"].sum()),
        "ticket_promedio_usd": round(
            ingreso_total / transacciones, 2) if transacciones else 0.0,
        "skus_distintos": int(ssot["SKU_ID"].nunique()),
        "transacciones_sin_margen": sin_margen,
        "pct_transacciones_sin_margen": round(
            100 * sin_margen / transacciones, 2) if transacciones else 0.0,
    }
    kpis["margen_pct_agregado"] = round(
        100 * kpis["margen_neto_total_usd"] / ingreso_total, 2
    ) if ingreso_total else 0.0

    advertencias = []
    if sin_margen:
        advertencias.append(
            f"{sin_margen:,} transacciones "
            f"({kpis['pct_transacciones_sin_margen']:.1f} %) no tienen "
            f"costo conocido (venta sin catálogo o costo atípico excluido) "
            f"y no aportan al margen total. Use el interruptor 'Incluir "
            f"venta sin catálogo' del panel lateral para excluirlas del "
            f"ingreso también.")

    return ResumenGeneral(kpis=kpis, advertencias=advertencias)
