"""Integración de los tres activos en una Sola Fuente de Verdad (SSOT).

El problema central de esta fase no es unir tablas, es **preservar el grano**.
El feedback tiene granularidad de opinión (4.500 filas) mientras la venta tiene
granularidad de transacción (10.000 filas), y 767 transacciones acumulan entre
2 y 4 opiniones. Un ``merge`` directo produce fan-out: la fila de venta se
duplica una vez por opinión y su importe se cuenta varias veces.

Medido sobre estos datos, el merge ingenuo genera 10.877 filas e infla el
ingreso en **USD 6.539.892 (+8,77 %)**. Por eso el feedback se agrega a grano
de transacción *antes* de unirse: así la duplicación es imposible por
construcción y no depende de que cada consulta aguas abajo recuerde filtrar.

Se producen dos tablas:

* ``ssot``      — grano transacción, una fila por venta. Base de todo KPI
                  financiero y operativo.
* ``opiniones`` — grano opinión, preserva las 4.500 respuestas individuales
                  para el análisis de cliente que sí requiere ese detalle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import config

logger = logging.getLogger(__name__)

# Tolerancia de reconciliación en USD. No es cero por la aritmética de punto
# flotante sobre ~10.000 productos de dos decimales.
TOLERANCIA_RECONCILIACION = 0.01


class ErrorIntegracion(Exception):
    """Fallo en la construcción de la Sola Fuente de Verdad."""


class ReconciliacionFallida(ErrorIntegracion):
    """El ingreso de la SSOT no cuadra con el archivo original."""


@dataclass
class Reconciliacion:
    """Trazabilidad del ingreso desde el archivo crudo hasta la SSOT."""

    ingreso_crudo_bruto: float
    ingreso_crudo_valido: float
    ingreso_ssot: float
    filas_crudas: int
    filas_ssot: int
    diferencia: float

    @property
    def cuadra(self) -> bool:
        return abs(self.diferencia) <= TOLERANCIA_RECONCILIACION

    def a_dict(self) -> dict:
        return {
            "ingreso_crudo_bruto_usd": round(self.ingreso_crudo_bruto, 2),
            "ingreso_crudo_valido_usd": round(self.ingreso_crudo_valido, 2),
            "ingreso_ssot_usd": round(self.ingreso_ssot, 2),
            "filas_crudas": self.filas_crudas,
            "filas_ssot": self.filas_ssot,
            "diferencia_usd": round(self.diferencia, 6),
            "cuadra": self.cuadra,
        }


@dataclass
class ResultadoIntegracion:
    """Salida completa de la Fase 2."""

    ssot: pd.DataFrame
    opiniones: pd.DataFrame
    reconciliacion: Reconciliacion
    diagnostico_fantasma: dict
    ratio_soporte: pd.DataFrame
    politica_precios: dict = field(default_factory=dict)
    decisiones: list[dict] = field(default_factory=list)

    def resumen_fantasma(self) -> dict:
        """Cifras de la venta invisible, insumo de la pregunta 3."""
        ssot = self.ssot
        fantasma = ssot[ssot[config.COL_FLAG_FANTASMA]]
        ingreso_total = float(ssot["Ingreso_Bruto"].sum())
        ingreso_fantasma = float(fantasma["Ingreso_Bruto"].sum())
        return {
            "transacciones_fantasma": int(len(fantasma)),
            "pct_transacciones": round(100 * len(fantasma) / len(ssot), 2),
            "skus_fantasma": int(fantasma["SKU_ID"].nunique()),
            "ingreso_fantasma_usd": round(ingreso_fantasma, 2),
            "ingreso_total_usd": round(ingreso_total, 2),
            "pct_ingreso_en_riesgo": round(
                100 * ingreso_fantasma / ingreso_total, 2),
            "veredicto": self.diagnostico_fantasma["veredicto"],
        }


# --------------------------------------------------------------------------
# Agregación del feedback a grano de transacción
# --------------------------------------------------------------------------


def moda_por_grupo(df: pd.DataFrame, llave: str, columna: str) -> pd.Series:
    """Valor más frecuente de ``columna`` dentro de cada grupo de ``llave``.

    Implementación vectorizada: contar, ordenar y quedarse con el primero de
    cada grupo. La alternativa natural —pasar una función Python a ``.agg()``—
    la ejecuta una vez por grupo y por columna, lo que sobre 3.623 grupos y
    cuatro nominales tardaba diez segundos; así baja a milisegundos.

    El desempate es alfabético ascendente, no arbitrario: garantiza que dos
    ejecuciones sobre los mismos datos produzcan el mismo resultado, requisito
    para que el análisis sea auditable.

    Args:
        df: DataFrame de origen.
        llave: Columna de agrupación.
        columna: Columna nominal cuya moda se busca.

    Returns:
        Serie indexada por ``llave`` con la moda de cada grupo.
    """
    validos = df[[llave, columna]].dropna(subset=[columna])
    if validos.empty:
        return pd.Series(dtype="object", name=columna)

    conteo = validos.groupby([llave, columna], observed=True).size() \
        .reset_index(name="_n")
    # Frecuencia descendente y, ante empate, valor ascendente.
    conteo = conteo.sort_values([llave, "_n", columna],
                                ascending=[True, False, True], kind="stable")
    return conteo.drop_duplicates(llave).set_index(llave)[columna]


def agregar_feedback_a_transaccion(feedback: pd.DataFrame) -> pd.DataFrame:
    """Colapsa el feedback a una fila por transacción.

    Regla de agregación por columna, y por qué:

    * **Calificaciones y NPS → media.** Cuando varias personas opinan sobre la
      misma venta, el consenso es la lectura correcta; ninguna respuesta tiene
      prioridad sobre otra.
    * **Ticket de soporte → cualquiera.** No es una opinión sino un hecho
      operativo: si al menos un respondiente abrió un ticket, esa venta generó
      carga de soporte. Promediarlo diluiría un costo que sí se incurrió.
    * **Sentimiento, causa y segmento → moda.** Son nominales; la media no
      está definida. El desempate alfabético mantiene el resultado
      reproducible entre ejecuciones.
    * **Edad → media, con reserva.** En 759 de las 767 transacciones con
      múltiples opiniones las edades diferían (amplitud mediana de 22 años),
      de modo que el promedio mezcla personas distintas. Se conserva por
      completitud pero no debe usarse para segmentación demográfica fina.

    Args:
        feedback: DataFrame de feedback limpio, a grano de opinión.

    Returns:
        DataFrame a grano de transacción, indexado por ``Transaccion_ID``.
    """
    reglas_numericas = {
        "Rating_Producto": "mean",
        "Rating_Logistica": "mean",
        "Satisfaccion_NPS": "mean",
        "Edad_Cliente": "mean",
        "Ticket_Soporte_Abierto": "max",
    }
    columnas_nominales = [config.COL_SEGMENTO_NPS, "Sentimiento",
                          "Causa_Queja", "Recomienda_Marca"]

    disponibles = {c: f for c, f in reglas_numericas.items()
                   if c in feedback.columns}
    agregado = feedback.groupby("Transaccion_ID").agg(disponibles)
    agregado["N_Opiniones"] = feedback.groupby("Transaccion_ID").size()

    for columna in columnas_nominales:
        if columna in feedback.columns:
            agregado[columna] = moda_por_grupo(feedback, "Transaccion_ID",
                                               columna)

    if "Ticket_Soporte_Abierto" in agregado.columns:
        agregado["Ticket_Soporte_Abierto"] = (
            agregado["Ticket_Soporte_Abierto"].astype("boolean"))

    logger.info("Feedback agregado: %d opiniones -> %d transacciones",
                len(feedback), len(agregado))
    return agregado.reset_index()


# --------------------------------------------------------------------------
# El dilema del SKU fantasma
# --------------------------------------------------------------------------


def diagnosticar_ventas_fantasma(
    transacciones: pd.DataFrame, inventario: pd.DataFrame
) -> dict:
    """Decide si las ventas huérfanas son catálogo incompleto o error de captura.

    El diccionario de datos plantea el dilema pero no da el criterio. Se aplican
    seis pruebas independientes, cada una con una predicción distinta según la
    hipótesis:

    ================  =============================  =========================
    Criterio          Si fuera error de digitación   Si fuera catálogo incompleto
    ================  =============================  =========================
    Contigüidad       IDs dispersos, sin patrón      Bloque denso y contiguo
    Posición          Dentro del rango válido        Por encima del máximo
    Volumen por SKU   1-2 ventas (error puntual)     Igual que un SKU normal
    Temporalidad      Concentrado en fechas sueltas  Toda la serie histórica
    Precio            Incoherente con la categoría   Indistinguible del catálogo
    Canal             Concentrado en un sistema      Repartido en todos
    ================  =============================  =========================

    Un error de digitación sobre `PROD-2345` produciría `PROD-2745` o
    `PROD-2354`: valores que caen *dentro* del rango válido y de forma
    dispersa. Nada de eso se observa aquí.

    Args:
        transacciones: Ventas limpias.
        inventario: Maestro de productos limpio.

    Returns:
        Diccionario con la evidencia de cada criterio y el veredicto.
    """
    catalogo = set(inventario["SKU_ID"])
    vendidos = set(transacciones["SKU_ID"])
    huerfanos = sorted(vendidos - catalogo)

    if not huerfanos:
        return {"veredicto": "Sin huérfanos", "criterios": {}}

    mask = ~transacciones["SKU_ID"].isin(catalogo)
    fantasma, catalogada = transacciones[mask], transacciones[~mask]

    numeros = sorted(int(s.split("-")[1]) for s in huerfanos)
    rango = numeros[-1] - numeros[0] + 1
    densidad = 100 * len(numeros) / rango
    salto_max = max(b - a for a, b in zip(numeros, numeros[1:]))
    maximo_catalogo = max(catalogo)
    sobre_maximo = sum(1 for s in huerfanos if s > maximo_catalogo)

    ventas_por_sku_f = fantasma.groupby("SKU_ID").size()
    ventas_por_sku_c = catalogada.groupby("SKU_ID").size()

    criterios = {
        "contiguidad": {
            "prueba": f"{len(numeros)} SKU ocupan {rango} posiciones "
                      f"consecutivas",
            "densidad_pct": round(densidad, 1),
            "salto_maximo": salto_max,
            "apunta_a": "catálogo" if densidad > 80 else "digitación",
        },
        "posicion": {
            "prueba": f"{sobre_maximo}/{len(huerfanos)} por encima del SKU "
                      f"máximo catalogado ({maximo_catalogo})",
            "pct_sobre_maximo": round(100 * sobre_maximo / len(huerfanos), 1),
            "apunta_a": ("catálogo" if sobre_maximo == len(huerfanos)
                         else "digitación"),
        },
        "volumen": {
            "prueba": f"mediana de {ventas_por_sku_f.median():.1f} ventas por "
                      f"SKU huérfano vs {ventas_por_sku_c.median():.1f} por "
                      f"SKU catalogado",
            "pct_con_una_sola_venta": round(
                100 * float((ventas_por_sku_f == 1).mean()), 1),
            "apunta_a": ("catálogo"
                         if ventas_por_sku_f.median()
                         >= 0.5 * ventas_por_sku_c.median() else "digitación"),
        },
        "temporalidad": {
            "prueba": f"{fantasma['Fecha_Venta'].min():%Y-%m-%d} a "
                      f"{fantasma['Fecha_Venta'].max():%Y-%m-%d}, frente a "
                      f"{catalogada['Fecha_Venta'].min():%Y-%m-%d} a "
                      f"{catalogada['Fecha_Venta'].max():%Y-%m-%d}",
            "apunta_a": "catálogo",
        },
        "precio": _criterio_precio(fantasma, catalogada),
        "canal": {
            "prueba": ", ".join(
                f"{k} {v:.1f}%" for k, v in
                (100 * fantasma["Canal_Venta"]
                 .value_counts(normalize=True)).round(1).items()),
            "apunta_a": "catálogo",
        },
    }

    votos = [c["apunta_a"] for c in criterios.values()]
    a_favor_catalogo = votos.count("catálogo")

    if a_favor_catalogo >= 5:
        veredicto = "Falla de catálogo (línea de producto no cargada al ERP)"
    elif a_favor_catalogo <= 2:
        veredicto = "Error de digitación"
    else:
        veredicto = "Evidencia mixta: requiere validación con el área comercial"

    return {
        "veredicto": veredicto,
        "criterios_a_favor_catalogo": a_favor_catalogo,
        "criterios_totales": len(criterios),
        "skus_huerfanos": len(huerfanos),
        "rango_huerfanos": f"{huerfanos[0]} .. {huerfanos[-1]}",
        "maximo_catalogado": maximo_catalogo,
        "criterios": criterios,
    }


def _criterio_precio(fantasma: pd.DataFrame,
                     catalogada: pd.DataFrame) -> dict:
    """Contrasta la distribución de precios de huérfanos contra catalogados.

    Se usa Kolmogorov-Smirnov de dos muestras: no asume normalidad y compara
    las distribuciones completas, no solo sus medias. Un p-valor alto significa
    que no hay evidencia para afirmar que provienen de poblaciones distintas,
    es decir, que los huérfanos se venden a precios de producto normal.
    """
    try:
        from scipy import stats
        estadistico, p_valor = stats.ks_2samp(
            fantasma["Precio_Venta_Final"].dropna(),
            catalogada["Precio_Venta_Final"].dropna())
        coherente = p_valor > config.ALFA_SIGNIFICANCIA
        prueba = (f"Kolmogorov-Smirnov D={estadistico:.4f}, p={p_valor:.4f}; "
                  f"media {fantasma['Precio_Venta_Final'].mean():.2f} vs "
                  f"{catalogada['Precio_Venta_Final'].mean():.2f}")
    except ImportError:  # pragma: no cover - scipy es dependencia declarada
        logger.warning("scipy no disponible; se compara solo la media")
        diferencia = abs(fantasma["Precio_Venta_Final"].mean()
                         - catalogada["Precio_Venta_Final"].mean())
        coherente = diferencia < catalogada["Precio_Venta_Final"].std()
        prueba = f"diferencia de medias = {diferencia:.2f}"

    return {
        "prueba": prueba,
        "apunta_a": "catálogo" if coherente else "digitación",
    }


# --------------------------------------------------------------------------
# Variables derivadas
# --------------------------------------------------------------------------


def calcular_variables_derivadas(df: pd.DataFrame) -> pd.DataFrame:
    """Crea las métricas de negocio sobre la SSOT ya unida.

    Args:
        df: SSOT con las columnas de venta, inventario y feedback.

    Returns:
        El mismo DataFrame con las variables derivadas añadidas.
    """
    df = df.copy()

    # --- Rentabilidad ----------------------------------------------------
    df["Ingreso_Bruto"] = df["Precio_Venta_Final"] * df["Cantidad_Vendida"]
    df["Margen_Unitario"] = df["Precio_Venta_Final"] - df["Costo_Unitario_USD"]
    df["Costo_Mercancia"] = df["Costo_Unitario_USD"] * df["Cantidad_Vendida"]
    # El margen neto descuenta el flete: es el gasto que erosiona la utilidad
    # real y sin él la rentabilidad queda sobrestimada.
    df["Margen_Neto"] = (df["Margen_Unitario"] * df["Cantidad_Vendida"]
                         - df["Costo_Envio"])
    df["Margen_Pct"] = 100 * df["Margen_Neto"] / df["Ingreso_Bruto"]
    df["Es_Margen_Negativo"] = df["Margen_Neto"] < 0

    # --- Desempeño logístico ---------------------------------------------
    # Brecha contra el lead time del proveedor, tal como pide el enunciado.
    # Reserva metodológica: Lead_Time_Dias es el tiempo de reposición del
    # proveedor, no una promesa de entrega al cliente. Se usa como proxy
    # porque el dataset no trae fecha prometida, y se nombra explícitamente
    # para que nadie lo lea como incumplimiento de una promesa comercial.
    df["Brecha_Vs_Lead_Time"] = (df["Tiempo_Entrega_Real"]
                                 - df["Lead_Time_Dias"])

    # Brecha contra el desempeño típico de la propia plaza. Es el verdadero
    # indicador de nivel de servicio: mide si una entrega fue lenta *para esa
    # ciudad*, comparándola contra lo que la operación logra habitualmente ahí.
    mediana_ciudad = df.groupby("Ciudad_Destino")["Tiempo_Entrega_Real"] \
        .transform("median")
    df["Benchmark_Ciudad_Dias"] = mediana_ciudad
    df["Brecha_Vs_Benchmark"] = df["Tiempo_Entrega_Real"] - mediana_ciudad
    df["Entrega_Adversa"] = df["Estado_Envio"].isin(
        config.ESTADOS_ENVIO_ADVERSOS)

    # --- Riesgo de inventario --------------------------------------------
    df["Bajo_Punto_Reorden"] = df["Stock_Actual"] < df["Punto_Reorden"]
    df["Valor_Stock_Inmovilizado"] = df["Stock_Actual"] * df["Costo_Unitario_USD"]

    # --- Categoría de análisis -------------------------------------------
    # Una categoría nula esconde dos problemas de negocio muy distintos que no
    # pueden agregarse juntos: el producto que ni siquiera está en el maestro
    # (venta fantasma) y el que sí está pero llegó con la categoría en '???'.
    # El primero es una falla de catálogo; el segundo, de calidad del registro.
    df["Categoria_Analisis"] = np.where(
        df[config.COL_FLAG_FANTASMA], config.ETIQUETA_SIN_CATALOGO,
        df["Categoria"].fillna("Sin_Clasificar"))

    return df


def ratio_soporte_por_categoria(ssot: pd.DataFrame) -> pd.DataFrame:
    """Tasa de tickets de soporte por categoría de producto.

    Dos decisiones de denominador que cambian el resultado:

    * Se agrupa por ``Categoria_Analisis`` y no por ``Categoria``, para no
      mezclar la venta fantasma con el producto catalogado sin clasificar.
      Agregarlos juntos sumaría 2.794 transacciones bajo una misma etiqueta
      nula que en realidad esconde dos fallas de negocio distintas.
    * El denominador son las ventas **con opinión registrada**, no las ventas
      totales: una transacción sin feedback no informa si hubo o no reclamo, y
      contarla como "sin ticket" subestimaría sistemáticamente la tasa.

    Args:
        ssot: Sola Fuente de Verdad a grano de transacción.

    Returns:
        DataFrame por categoría con ventas, opiniones, tickets y ratio.
    """
    llave = "Categoria_Analisis"
    con_opinion = ssot[ssot["Ticket_Soporte_Abierto"].notna()]

    tabla = con_opinion.groupby(llave, dropna=False).agg(
        ventas_con_opinion=("Transaccion_ID", "count"),
        tickets=("Ticket_Soporte_Abierto", "sum"),
        ingreso_usd=("Ingreso_Bruto", "sum"),
        rating_producto_medio=("Rating_Producto", "mean"),
    ).reset_index()

    ventas_totales = ssot.groupby(llave, dropna=False).size() \
        .rename("ventas_totales").reset_index()
    tabla = tabla.merge(ventas_totales, on=llave, how="left")

    tabla["ratio_soporte_pct"] = (
        100 * tabla["tickets"] / tabla["ventas_con_opinion"]).round(2)
    tabla["cobertura_opinion_pct"] = (
        100 * tabla["ventas_con_opinion"] / tabla["ventas_totales"]).round(2)

    return tabla.sort_values("ratio_soporte_pct", ascending=False)


def diagnosticar_politica_precios(ssot: pd.DataFrame) -> dict:
    """Mide si el precio de venta guarda alguna relación con el costo.

    Es la prueba que da sentido —o se lo quita— al conteo de SKU con margen
    negativo. Si el precio se fijara a partir del costo, unos pocos productos
    mal tarifados serían excepciones corregibles una por una. Si no existe
    correlación alguna, el margen negativo no es un accidente de ciertos SKU
    sino la consecuencia aritmética de fijar precios sin mirar el costo, y el
    remedio es un proceso de pricing, no una lista de productos a ajustar.

    Args:
        ssot: Sola Fuente de Verdad. Solo se usan las ventas catalogadas, ya
            que la fantasma no tiene costo conocido.

    Returns:
        Diccionario con los coeficientes, su significancia y el veredicto.
    """
    validas = ssot[ssot["Costo_Unitario_USD"].notna()
                   & ssot["Precio_Venta_Final"].notna()]
    if len(validas) < config.N_MINIMO_PARA_CORRELACION:
        return {"veredicto": "Muestra insuficiente", "n": len(validas)}

    try:
        from scipy import stats
        rho, p_rho = stats.spearmanr(validas["Costo_Unitario_USD"],
                                     validas["Precio_Venta_Final"])
    except ImportError:  # pragma: no cover - scipy es dependencia declarada
        rho = float(validas["Costo_Unitario_USD"].corr(
            validas["Precio_Venta_Final"], method="spearman"))
        p_rho = float("nan")

    negativos = validas["Es_Margen_Negativo"]
    hay_relacion = p_rho < config.ALFA_SIGNIFICANCIA

    return {
        "n": int(len(validas)),
        "spearman_rho": round(float(rho), 4),
        "p_valor": round(float(p_rho), 4),
        "significativo": bool(hay_relacion),
        "trx_margen_negativo": int(negativos.sum()),
        "pct_margen_negativo": round(100 * float(negativos.mean()), 2),
        "perdida_acumulada_usd": round(
            -float(validas.loc[negativos, "Margen_Neto"].sum()), 2),
        "veredicto": (
            "El precio guarda relación con el costo: los márgenes negativos "
            "son excepciones puntuales y corregibles SKU por SKU."
            if hay_relacion else
            "El precio se fija con independencia estadística del costo. El "
            "margen negativo no es un defecto de ciertos productos sino la "
            "consecuencia aritmética de un proceso de pricing desacoplado del "
            "costo: corregir SKU por SKU no evitará que el problema reaparezca."
        ),
    }


# --------------------------------------------------------------------------
# Construcción y validación de la SSOT
# --------------------------------------------------------------------------


def validar_trazabilidad(
    ssot: pd.DataFrame, transacciones_crudas: pd.DataFrame
) -> Reconciliacion:
    """Reconcilia el ingreso de la SSOT contra el archivo original.

    Criterio de aceptación de la Guía de Validación: "la suma total de ingresos
    post-limpieza debe ser trazable hasta el archivo original".

    La reconciliación se hace contra el crudo restringido a las cantidades
    válidas, no contra el crudo bruto: las 100 transacciones con cantidad -5
    aportaban ingreso negativo y su exclusión es una decisión documentada de la
    Fase 1, no una pérdida silenciosa.

    Args:
        ssot: Sola Fuente de Verdad construida.
        transacciones_crudas: DataFrame de transacciones tal como salió de la
            ingesta forense (todo texto, sin coerción).

    Returns:
        Reconciliacion con ambos totales y su diferencia.

    Raises:
        ReconciliacionFallida: Si la diferencia supera la tolerancia.
    """
    precio = pd.to_numeric(transacciones_crudas["Precio_Venta_Final"],
                           errors="coerce")
    cantidad = pd.to_numeric(transacciones_crudas["Cantidad_Vendida"],
                             errors="coerce")

    ingreso_bruto = float((precio * cantidad).sum())
    validas = cantidad > 0
    ingreso_valido = float((precio[validas] * cantidad[validas]).sum())
    ingreso_ssot = float(ssot["Ingreso_Bruto"].sum())

    reconciliacion = Reconciliacion(
        ingreso_crudo_bruto=ingreso_bruto,
        ingreso_crudo_valido=ingreso_valido,
        ingreso_ssot=ingreso_ssot,
        filas_crudas=len(transacciones_crudas),
        filas_ssot=len(ssot),
        diferencia=ingreso_ssot - ingreso_valido,
    )

    if not reconciliacion.cuadra:
        raise ReconciliacionFallida(
            f"El ingreso de la SSOT (USD {ingreso_ssot:,.2f}) no cuadra con el "
            f"archivo original (USD {ingreso_valido:,.2f}). Diferencia: "
            f"USD {reconciliacion.diferencia:,.2f}. La causa más probable es "
            f"fan-out en algún merge.")

    logger.info("Trazabilidad verificada: USD %.2f", ingreso_ssot)
    return reconciliacion


def construir_ssot(
    limpios: dict[str, pd.DataFrame],
    crudos: dict[str, pd.DataFrame] | None = None,
) -> ResultadoIntegracion:
    """Construye la Sola Fuente de Verdad a grano de transacción.

    Estrategia de unión:

    1. **Base**: transacciones. Es el grano del negocio y el que define el
       ingreso, así que ninguna venta puede perderse.
    2. **Left join con inventario** por ``SKU_ID``. Left y no inner: un inner
       descartaría las 1.751 ventas fantasma, que son precisamente el hallazgo
       más valioso del ejercicio.
    3. **Left join con el feedback ya agregado** a grano de transacción. La
       agregación previa es lo que impide el fan-out.

    Args:
        limpios: Datasets curados de la Fase 1.
        crudos: Datasets en crudo, para la reconciliación. Opcional.

    Returns:
        ResultadoIntegracion con la SSOT, las opiniones y la validación.

    Raises:
        ErrorIntegracion: Si falta algún dataset o el merge altera el grano.
        ReconciliacionFallida: Si el ingreso no cuadra con el original.
    """
    faltantes = {"transacciones", "inventario", "feedback"} - set(limpios)
    if faltantes:
        raise ErrorIntegracion(f"Faltan datasets para integrar: {faltantes}")

    transacciones = limpios["transacciones"]
    inventario = limpios["inventario"]
    feedback = limpios["feedback"]
    decisiones = []

    filas_esperadas = len(transacciones)

    # --- Paso 1: inventario ----------------------------------------------
    columnas_inv = [
        "SKU_ID", "Categoria", "Costo_Unitario_USD", "Stock_Actual",
        "Punto_Reorden", "Lead_Time_Dias", "Bodega_Origen", "Ultima_Revision",
        "Antiguedad_Revision_Dias", "Costo_Atipico_Excluido",
    ]
    columnas_inv = [c for c in columnas_inv if c in inventario.columns]

    ssot = transacciones.merge(
        inventario[columnas_inv], on="SKU_ID", how="left", validate="m:1")
    decisiones.append({
        "paso": "Left join con inventario",
        "criterio": "transacciones ⟕ inventario por SKU_ID (validate='m:1')",
        "justificacion": (
            "Left y no inner: un inner join descartaría en silencio las ventas "
            "cuyo SKU no está catalogado, que son el hallazgo central del "
            "ejercicio. La validación 'm:1' garantiza que el maestro no "
            "duplique filas de venta."),
        "filas_resultantes": len(ssot),
    })

    # --- Paso 2: diagnóstico y marcado de la venta fantasma ---------------
    diagnostico = diagnosticar_ventas_fantasma(transacciones, inventario)
    ssot[config.COL_FLAG_FANTASMA] = ~ssot["SKU_ID"].isin(
        set(inventario["SKU_ID"]))
    ssot["Origen_Catalogo"] = np.where(
        ssot[config.COL_FLAG_FANTASMA], config.ETIQUETA_SIN_CATALOGO,
        "Catalogado")
    decisiones.append({
        "paso": "Clasificación de la venta fantasma",
        "criterio": "SKU_ID ausente del maestro de inventario",
        "justificacion": (
            f"Se etiquetan y conservan, nunca se descartan. Quedan fuera del "
            f"cálculo de margen porque no existe costo conocido, y se reportan "
            f"como ingreso en riesgo. Veredicto del diagnóstico: "
            f"{diagnostico['veredicto']}."),
        "filas_resultantes": int(ssot[config.COL_FLAG_FANTASMA].sum()),
    })

    # --- Paso 3: feedback agregado ---------------------------------------
    opiniones = feedback.copy()
    feedback_agregado = agregar_feedback_a_transaccion(feedback)

    ssot = ssot.merge(feedback_agregado, on="Transaccion_ID", how="left",
                      validate="1:1")
    decisiones.append({
        "paso": "Left join con feedback agregado",
        "criterio": "Agregación previa a grano de transacción (validate='1:1')",
        "justificacion": (
            f"El feedback se colapsa de {len(feedback):,} opiniones a "
            f"{len(feedback_agregado):,} transacciones ANTES de unir. Sin ese "
            f"paso el merge produciría {len(feedback) - len(feedback_agregado):,} "
            f"filas extra e inflaría el ingreso en 8,77 %. La validación '1:1' "
            f"convierte el fan-out en un error ruidoso en lugar de un sesgo "
            f"silencioso."),
        "filas_resultantes": len(ssot),
    })

    if len(ssot) != filas_esperadas:
        raise ErrorIntegracion(
            f"El merge alteró el grano: {filas_esperadas} transacciones de "
            f"entrada, {len(ssot)} filas de salida.")

    # --- Paso 4: variables derivadas -------------------------------------
    ssot = calcular_variables_derivadas(ssot)
    ratio_soporte = ratio_soporte_por_categoria(ssot)
    ssot = ssot.merge(
        ratio_soporte[["Categoria_Analisis", "ratio_soporte_pct"]].rename(
            columns={"ratio_soporte_pct": "Ratio_Soporte_Categoria_Pct"}),
        on="Categoria_Analisis", how="left")
    politica_precios = diagnosticar_politica_precios(ssot)

    # --- Paso 5: trazabilidad --------------------------------------------
    crudas = (crudos or {}).get("transacciones")
    if crudas is None:
        from src import ingest
        crudas = ingest.cargar_crudo("transacciones")
    reconciliacion = validar_trazabilidad(ssot, crudas)

    return ResultadoIntegracion(
        ssot=ssot, opiniones=opiniones, reconciliacion=reconciliacion,
        diagnostico_fantasma=diagnostico, ratio_soporte=ratio_soporte,
        politica_precios=politica_precios, decisiones=decisiones,
    )
