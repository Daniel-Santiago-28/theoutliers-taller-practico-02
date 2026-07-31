"""Limpieza y curaduría de los activos de información de TechLogistics.

Principios que rigen este módulo:

1. **Nada se borra en silencio.** Todo registro excluido queda disponible en
   ``RegistroLimpieza.excluidos`` para que el dashboard pueda mostrarlo.
2. **La estrategia de imputación se deriva de los datos, no se asume.**
   ``_elegir_estrategia`` mide la asimetría de cada columna y decide media o
   mediana según la regla de Bulmer. El estadístico que motivó la decisión
   queda registrado, de modo que la justificación del informe de hallazgos es
   reproducible y no una afirmación del consultor.
3. **No imputar también es una decisión, y se documenta.** Rellenar una
   nominal casi uniforme con su moda fabrica señal en la dimensión por la que
   luego se segmenta el análisis. Cuando eso ocurre, se deja el nulo y se
   registra el porqué.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from src import config

logger = logging.getLogger(__name__)

# Regla de Bulmer: |asimetría| < 0.5 se considera aproximadamente simétrica.
UMBRAL_ASIMETRIA = 0.5

# Entropía normalizada por encima de la cual una nominal se considera
# demasiado uniforme para que su moda sea representativa.
UMBRAL_ENTROPIA_UNIFORME = 0.95

# Sufijo de las banderas que distinguen un valor estimado de uno observado.
SUFIJO_IMPUTADO = "_Imputado"


# --------------------------------------------------------------------------
# Bitácora de limpieza
# --------------------------------------------------------------------------


@dataclass
class AccionLimpieza:
    """Una decisión de curaduría, con su evidencia estadística."""

    dataset: str
    columna: str
    accion: str
    criterio: str
    justificacion: str
    filas_afectadas: int
    valor_aplicado: str = ""
    evidencia: str = ""

    def a_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "columna": self.columna,
            "accion": self.accion,
            "criterio": self.criterio,
            "filas_afectadas": self.filas_afectadas,
            "valor_aplicado": self.valor_aplicado,
            "evidencia_estadistica": self.evidencia,
            "justificacion": self.justificacion,
        }


@dataclass
class RegistroLimpieza:
    """Bitácora completa: qué se hizo, por qué y qué quedó excluido."""

    acciones: list[AccionLimpieza] = field(default_factory=list)
    excluidos: dict[str, pd.DataFrame] = field(default_factory=dict)

    def agregar(self, **kwargs) -> None:
        """Registra una acción de limpieza."""
        self.acciones.append(AccionLimpieza(**kwargs))

    def excluir(self, etiqueta: str, filas: pd.DataFrame) -> None:
        """Archiva registros excluidos para consulta posterior en la UI."""
        if not filas.empty:
            self.excluidos[etiqueta] = filas.copy()

    def a_dataframe(self) -> pd.DataFrame:
        """Bitácora como tabla, base del reporte descargable."""
        if not self.acciones:
            return pd.DataFrame()
        return pd.DataFrame([a.a_dict() for a in self.acciones])

    def fusionar(self, otro: RegistroLimpieza) -> None:
        """Incorpora la bitácora de otro dataset a esta."""
        self.acciones.extend(otro.acciones)
        self.excluidos.update(otro.excluidos)


# --------------------------------------------------------------------------
# Selección de estrategia de imputación guiada por la distribución
# --------------------------------------------------------------------------


def _elegir_estrategia(serie: pd.Series) -> tuple[str, float, str]:
    """Decide media o mediana midiendo la asimetría de la distribución.

    Se aplica la regla de Bulmer: una distribución con |asimetría| < 0.5 se
    considera aproximadamente simétrica, caso en que la media es el estimador
    de tendencia central más eficiente. Con asimetría mayor, la media se
    desplaza hacia la cola y la mediana es el estimador robusto.

    Args:
        serie: Serie numérica ya libre de valores inválidos.

    Returns:
        Tupla (estrategia, valor_a_imputar, evidencia legible).
    """
    validos = serie.dropna()
    if validos.empty:
        return "ninguna", np.nan, "sin datos válidos para estimar"

    asimetria = float(validos.skew()) if len(validos) > 2 else 0.0
    curtosis = float(validos.kurtosis()) if len(validos) > 3 else 0.0
    media, mediana = float(validos.mean()), float(validos.median())

    if abs(asimetria) < UMBRAL_ASIMETRIA:
        evidencia = (
            f"asimetría={asimetria:.3f} (|a|<{UMBRAL_ASIMETRIA}, simétrica), "
            f"curtosis={curtosis:.3f}, media={media:.2f} ≈ mediana={mediana:.2f}"
        )
        return "media", media, evidencia

    desvio = 100 * (media - mediana) / mediana if mediana else float("inf")
    evidencia = (
        f"asimetría={asimetria:.3f} (|a|≥{UMBRAL_ASIMETRIA}, sesgada), "
        f"curtosis={curtosis:.3f}, media={media:.2f} supera a la mediana="
        f"{mediana:.2f} en {desvio:.1f}%"
    )
    return "mediana", mediana, evidencia


def _entropia_normalizada(serie: pd.Series) -> float:
    """Entropía de Shannon normalizada (0 = un solo valor, 1 = uniforme)."""
    frecuencias = serie.dropna().value_counts(normalize=True)
    if len(frecuencias) <= 1:
        return 0.0
    entropia = -(frecuencias * np.log2(frecuencias)).sum()
    return float(entropia / np.log2(len(frecuencias)))


def sufijo_imputado(columna: str) -> str:
    """Nombre de la bandera que marca los valores imputados de una columna."""
    return f"{columna}{SUFIJO_IMPUTADO}"


def _imputar_numerica(
    df: pd.DataFrame, columna: str, dataset: str, log: RegistroLimpieza,
    justificacion: str,
) -> None:
    """Imputa nulos de una columna numérica con la estrategia que dicten los datos.

    Siempre deja una bandera ``<columna>_Imputado`` a nivel de fila, incluso
    cuando no hubo nada que imputar. Sin ella, un valor estimado sería
    indistinguible de uno observado en el resto del análisis: la imputación por
    media clava los faltantes en el centro exacto de la distribución, lo que
    contrae la varianza y atenúa cualquier correlación que use esa columna. La
    bandera permite excluirlos cuando se analice dispersión o correlación.
    """
    mask_faltante = df[columna].isna()
    faltantes = int(mask_faltante.sum())
    df[sufijo_imputado(columna)] = mask_faltante

    if not faltantes:
        return

    estrategia, valor, evidencia = _elegir_estrategia(df[columna])
    if estrategia == "ninguna":
        return

    # pandas infiere Int64 en columnas sin decimales y rechaza el relleno con
    # un flotante. Se promueve a Float64 antes de imputar.
    df[columna] = df[columna].astype("Float64").fillna(valor)
    log.agregar(
        dataset=dataset, columna=columna, accion=f"Imputación por {estrategia}",
        criterio=f"Regla de Bulmer sobre la asimetría de {columna}",
        justificacion=justificacion, filas_afectadas=faltantes,
        valor_aplicado=f"{valor:.2f}",
        evidencia=f"{evidencia}; marcados en {sufijo_imputado(columna)}",
    )


def _imputar_cantidad_por_sku(
    df: pd.DataFrame, mask_faltante: pd.Series, dataset: str, log: RegistroLimpieza,
) -> None:
    """Imputa ``Cantidad_Vendida`` con la mediana de las demás ventas válidas
    del mismo SKU_ID, con respaldo en la mediana global.

    El costo unitario no sirve como predictor: sobre las ventas válidas, la
    correlación de Spearman entre Costo_Unitario_USD y Cantidad_Vendida es
    ≈ -0,015 (ruido), y la mediana de unidades es prácticamente idéntica en
    los cuatro cuartiles de costo (7-8 unidades en Q1...Q4). El SKU sí aporta
    algo que un promedio ciego del catálogo no: ancla la imputación al
    historial real de ese producto específico, en vez de mezclar bajo un
    único número transacciones de escalas de precio muy distintas. Los
    SKU sin ninguna venta válida propia (PROD-1899, PROD-1309) caen en la
    mediana global.
    """
    mediana_sku = df.groupby("SKU_ID")["Cantidad_Vendida"].transform("median")
    mediana_global = float(df["Cantidad_Vendida"].median())

    resultado = (df["Cantidad_Vendida"].astype("Float64")
                 .fillna(mediana_sku).fillna(mediana_global).round())

    n_por_sku = int((mask_faltante & mediana_sku.notna()).sum())
    n_respaldo_global = int((mask_faltante & mediana_sku.isna()).sum())
    skus_respaldo = sorted(
        df.loc[mask_faltante & mediana_sku.isna(), "SKU_ID"].unique())

    df[sufijo_imputado("Cantidad_Vendida")] = mask_faltante
    df["Cantidad_Vendida"] = resultado
    log.agregar(
        dataset=dataset, columna="Cantidad_Vendida",
        accion="Imputación por mediana de SKU_ID (con respaldo global)",
        criterio=("Mediana de las ventas válidas del mismo SKU_ID; mediana "
                  "global si el SKU no tiene ninguna venta válida propia"),
        justificacion=(
            "Se prefiere a dejarlo nulo porque estas 100 transacciones "
            "vuelven a aportar a Ingreso_Bruto y al análisis de "
            "rentabilidad, con trazabilidad completa vía la bandera "
            "Cantidad_Vendida_Imputado. El costo no se usa como predictor "
            "porque no correlaciona con la cantidad en este dataset; el SKU "
            "sí, porque cada producto trae consigo su propio historial de "
            "ventas y evita mezclar bajo un solo número productos de "
            "escalas de precio muy distintas."),
        filas_afectadas=int(mask_faltante.sum()),
        valor_aplicado="mediana por SKU_ID, redondeada al entero más cercano",
        evidencia=(
            f"correlación de Spearman costo-cantidad ≈ -0.015 (no "
            f"informativa); {n_por_sku} filas imputadas con la mediana de su "
            f"propio SKU; {n_respaldo_global} filas sin ninguna venta válida "
            f"propia ({', '.join(skus_respaldo)}) usaron la mediana global "
            f"de {mediana_global:.0f} unidades"),
    )


def _normalizar_categorica(
    serie: pd.Series, mapa: dict[str, str]
) -> pd.Series:
    """Aplica un diccionario de mapeo sobre la forma canónica (minúsculas)."""
    clave = serie.astype("string").str.strip().str.lower()
    return clave.map(mapa).astype("string")


def _a_nulo_centinelas(serie: pd.Series) -> pd.Series:
    """Convierte los centinelas de texto en nulos reales."""
    texto = serie.astype("string").str.strip()
    centinelas = {c.strip().lower() for c in config.CENTINELAS_NULOS if c.strip()}
    return texto.mask(texto.str.lower().isin(centinelas) | (texto == ""))


# --------------------------------------------------------------------------
# Limpieza: Inventario
# --------------------------------------------------------------------------


def limpiar_inventario(crudo: pd.DataFrame) -> tuple[pd.DataFrame, RegistroLimpieza]:
    """Cura el maestro de productos.

    Args:
        crudo: DataFrame de inventario tal como sale de ``ingest``.

    Returns:
        Tupla (DataFrame limpio y tipado, bitácora de decisiones).
    """
    df = crudo.copy()
    log = RegistroLimpieza()
    ds = "inventario"

    # --- Categoría: colapsar variantes y decidir sobre '???' -------------
    original = df["Categoria"].copy()
    df["Categoria"] = _normalizar_categorica(df["Categoria"],
                                             config.MAPA_CATEGORIAS)
    unificados = int((_a_nulo_centinelas(original).str.strip()
                      != df["Categoria"]).fillna(False).sum())
    log.agregar(
        dataset=ds, columna="Categoria", accion="Normalización de variantes",
        criterio="Diccionario de mapeo sobre forma canónica en minúsculas",
        justificacion=(
            "'LAPTOP'/'Laptops' y 'smart-phone'/'Smartphones' son la misma "
            "categoría de negocio escrita por dos sistemas distintos. Sin "
            "unificarlas, el filtro del sidebar mostraría ocho opciones para "
            "cinco realidades y los márgenes por categoría se calcularían "
            "sobre poblaciones partidas por la mitad."),
        filas_afectadas=unificados, valor_aplicado="8 variantes → 5 categorías",
    )

    faltantes_cat = int(df["Categoria"].isna().sum())
    entropia = _entropia_normalizada(df["Categoria"])
    moda_share = df["Categoria"].value_counts(normalize=True).iloc[0]
    log.agregar(
        dataset=ds, columna="Categoria", accion="NO imputar (nulo deliberado)",
        criterio=f"Entropía normalizada > {UMBRAL_ENTROPIA_UNIFORME}",
        justificacion=(
            "La distribución de categorías es casi uniforme: ninguna moda "
            "domina. Imputar con la moda inyectaría un 12 % de masa artificial "
            "en una sola categoría, y la categoría es justamente la dimensión "
            "por la que se segmenta la pregunta de fidelidad. Se prefiere la "
            "ignorancia declarada al dato fabricado."),
        filas_afectadas=faltantes_cat, valor_aplicado="se conserva como nulo",
        evidencia=(f"entropía normalizada={entropia:.4f}, "
                   f"moda cubre solo {100 * moda_share:.1f}% de los válidos"),
    )

    # --- Bodega de origen -------------------------------------------------
    antes_bodega = df["Bodega_Origen"].copy()
    df["Bodega_Origen"] = _normalizar_categorica(df["Bodega_Origen"],
                                                 config.MAPA_BODEGAS)
    log.agregar(
        dataset=ds, columna="Bodega_Origen", accion="Normalización de mayúsculas",
        criterio="Diccionario de mapeo",
        justificacion=(
            "'norte' y 'Norte' son el mismo nodo de despacho. Se conservan "
            "'Zona_Franca' y 'BOD-EXT-99' como bodegas legítimas pese a su "
            "nomenclatura no regional: son candidatas naturales a operar sin "
            "control en el análisis de riesgo operativo."),
        filas_afectadas=int((antes_bodega != df["Bodega_Origen"]).sum()),
        valor_aplicado="6 variantes → 5 bodegas",
    )

    # --- Stock actual: negativos y nulos ---------------------------------
    df["Stock_Actual"] = pd.to_numeric(df["Stock_Actual"], errors="coerce")
    mask_negativo = df["Stock_Actual"] < 0
    n_negativos = int(mask_negativo.sum())
    if n_negativos:
        log.excluir("inventario_stock_negativo", crudo.loc[mask_negativo])
        df["Stock_Negativo_Corregido"] = mask_negativo
        df.loc[mask_negativo, "Stock_Actual"] = 0
        log.agregar(
            dataset=ds, columna="Stock_Actual",
            accion="Truncamiento a cero con bandera",
            criterio="Piso físico: no existe inventario negativo",
            justificacion=(
                "Un stock negativo es un artefacto contable de salidas no "
                "registradas que exceden el inventario del sistema. El piso "
                "físicamente interpretable es cero. Se trunca en vez de "
                "eliminar la fila para no perder el SKU del maestro, y se "
                "marca con bandera porque la magnitud del descuadre es "
                "evidencia de bodegas sin control de inventario."),
            filas_afectadas=n_negativos, valor_aplicado="0",
            evidencia=f"mínimo observado={crudo.loc[mask_negativo].shape[0]} "
                      f"registros, stock mínimo={df['Stock_Actual'].min():.0f} "
                      f"tras corrección",
        )
    else:
        df["Stock_Negativo_Corregido"] = False

    _imputar_numerica(
        df, "Stock_Actual", ds, log,
        justificacion=(
            "La distribución de existencias es simétrica y platicúrtica "
            "(prácticamente uniforme entre 0 y 2.000 unidades). Sin cola que "
            "desplace el centro, la media es el estimador insesgado de menor "
            "varianza y coincide con la mediana, lo que confirma la simetría."),
    )

    # --- Costo unitario: outliers por IQR y piso de negocio --------------
    df["Costo_Unitario_USD"] = pd.to_numeric(df["Costo_Unitario_USD"],
                                             errors="coerce")
    from src.audit import detectar_outliers_iqr  # import local: evita ciclo

    mask_iqr, lim_inf, lim_sup = detectar_outliers_iqr(df["Costo_Unitario_USD"])
    mask_piso = df["Costo_Unitario_USD"] < 1
    mask_atipico = (mask_iqr | mask_piso).fillna(False)
    n_atipicos = int(mask_atipico.sum())

    if n_atipicos:
        excluidos = crudo.loc[mask_atipico].copy()
        excluidos["motivo_exclusion"] = np.where(
            mask_piso[mask_atipico], "Costo < USD 1 (piso de negocio)",
            f"Fuera del rango de Tukey [{lim_inf:.2f}, {lim_sup:.2f}]")
        log.excluir("inventario_costo_atipico", excluidos)

    df["Costo_Atipico_Excluido"] = mask_atipico
    df.loc[mask_atipico, "Costo_Unitario_USD"] = np.nan
    log.agregar(
        dataset=ds, columna="Costo_Unitario_USD",
        accion="Exclusión del cálculo (registro conservado)",
        criterio=f"Tukey IQR×{config.FACTOR_IQR} + piso de negocio de USD 1",
        justificacion=(
            "El filtro de Tukey captura el costo de USD 850.000, pero su valla "
            "inferior es negativa y por tanto no detecta el costo de USD 0,05. "
            "Ese registro necesita una regla de dominio: en electrónica de "
            "consumo un costo unitario bajo USD 1 no es un precio, es un error "
            "de captura. Si no se excluye, ese SKU produce un margen ficticio "
            "de +99,99 % que contamina el ranking de rentabilidad."),
        filas_afectadas=n_atipicos,
        valor_aplicado="nulo, con bandera Costo_Atipico_Excluido",
        evidencia=(f"valla de Tukey=[{lim_inf:.2f}, {lim_sup:.2f}]; "
                   f"{int(mask_iqr.sum())} por IQR + {int(mask_piso.sum())} "
                   f"por piso de negocio"),
    )

    # --- Lead time: texto mixto a numérico -------------------------------
    df["Lead_Time_Dias"] = _convertir_lead_time(df["Lead_Time_Dias"], ds, log)
    _imputar_numerica(
        df, "Lead_Time_Dias", ds, log,
        justificacion=(
            "La distribución de lead times es multimodal y con sesgo positivo: "
            "el bucket '25-30 días' arrastra la media muy por encima de la "
            "mediana. Usar la media sobrestimaría el tiempo típico de "
            "reposición y haría ver más lentos de lo que son los proveedores "
            "rápidos. La mediana es robusta a esa cola."),
    )

    # --- Última revisión --------------------------------------------------
    corte_inventario = config.fecha_corte()
    df["Ultima_Revision"] = pd.to_datetime(
        df["Ultima_Revision"], format=config.FORMATO_FECHA_INVENTARIO,
        errors="coerce")
    df["Antiguedad_Revision_Dias"] = (
        pd.Timestamp(corte_inventario) - df["Ultima_Revision"]).dt.days
    log.agregar(
        dataset=ds, columna="Ultima_Revision",
        accion="Tipado a fecha y derivación de antigüedad",
        criterio=f"Formato ISO {config.FORMATO_FECHA_INVENTARIO} contra la "
                 f"fecha de ejecución ({corte_inventario})",
        justificacion=(
            "La antigüedad del último conteo físico es el insumo directo de la "
            "pregunta de riesgo operativo: mide hace cuánto una bodega opera "
            "sobre stock teórico en vez de verificado."),
        filas_afectadas=int(df["Ultima_Revision"].notna().sum()),
        evidencia=(f"mediana de antigüedad="
                   f"{df['Antiguedad_Revision_Dias'].median():.0f} días, "
                   f"máximo={df['Antiguedad_Revision_Dias'].max():.0f} días"),
    )

    df["Punto_Reorden"] = pd.to_numeric(df["Punto_Reorden"], errors="coerce")
    return df, log


def _convertir_lead_time(
    serie: pd.Series, dataset: str, log: RegistroLimpieza
) -> pd.Series:
    """Convierte Lead_Time_Dias de texto mixto a numérico."""
    texto = serie.astype("string").str.strip().str.lower()
    mapeados = texto.map(config.MAPA_LEAD_TIME_TEXTO).astype("Float64")
    # Float64 explícito: el punto medio 27.5 no cabe en el Int64 que pandas
    # infiere a partir de los valores enteros ('3', '5', '10').
    numericos = pd.to_numeric(texto, errors="coerce").astype("Float64")
    resultado = numericos.fillna(mapeados)

    n_rango = int(texto.isin(["25-30 días", "25-30 dias"]).sum())
    n_inmediato = int((texto == "inmediato").sum())
    log.agregar(
        dataset=dataset, columna="Lead_Time_Dias",
        accion="Conversión de texto a numérico",
        criterio="Punto medio del intervalo y equivalencia semántica",
        justificacion=(
            "'25-30 días' es un dato censurado por intervalo: su punto medio "
            "(27,5) es la imputación estándar porque no sesga hacia ningún "
            "extremo del rango declarado. 'Inmediato' significa disponibilidad "
            "sin espera de reposición, es decir cero días. Sin esta conversión "
            "el 52 % de la columna sería inutilizable para planeación."),
        filas_afectadas=n_rango + n_inmediato,
        valor_aplicado="'25-30 días'→27.5 ; 'Inmediato'→0.0",
        evidencia=f"{n_rango} registros de rango + {n_inmediato} inmediatos",
    )
    return resultado


# --------------------------------------------------------------------------
# Limpieza: Transacciones
# --------------------------------------------------------------------------


def limpiar_transacciones(
    crudo: pd.DataFrame,
) -> tuple[pd.DataFrame, RegistroLimpieza]:
    """Cura el histórico de ventas y ejecución logística."""
    df = crudo.copy()
    log = RegistroLimpieza()
    ds = "transacciones"

    # --- Fecha de venta ---------------------------------------------------
    df["Fecha_Venta"] = pd.to_datetime(
        df["Fecha_Venta"], format=config.FORMATO_FECHA_TRANSACCIONES,
        errors="coerce")
    hoy = config.fecha_corte()
    corte = pd.Timestamp(hoy)
    mask_futura = (df["Fecha_Venta"] > corte).fillna(False)
    df["Fecha_Futura"] = mask_futura
    if mask_futura.any():
        log.excluir("transacciones_fecha_futura", crudo.loc[mask_futura])
    log.agregar(
        dataset=ds, columna="Fecha_Venta",
        accion="Estandarización y marcado de fechas futuras",
        criterio=f"Formato {config.FORMATO_FECHA_TRANSACCIONES}; validación "
                 f"temporal contra datetime.now() ({hoy})",
        justificacion=(
            "Una venta no puede estar registrada en el futuro: si la fecha "
            "supera el momento de ejecución, el registro es un error de "
            "captura del sistema origen. Las ventas afectadas se marcan en vez "
            "de eliminarse, de modo que el ingreso total siga siendo trazable "
            "al archivo original, pero se excluyen de las series de tiempo "
            "para no mostrar actividad fuera del periodo real de operación."),
        filas_afectadas=int(mask_futura.sum()),
        valor_aplicado="bandera Fecha_Futura",
        evidencia=(f"rango {df['Fecha_Venta'].min():%Y-%m-%d} a "
                   f"{df['Fecha_Venta'].max():%Y-%m-%d}; "
                   f"{int(df['Fecha_Venta'].isna().sum())} no parseables; "
                   f"evaluado contra {hoy}"),
    )

    # --- Cantidad vendida -------------------------------------------------
    df["Cantidad_Vendida"] = pd.to_numeric(df["Cantidad_Vendida"],
                                           errors="coerce")
    mask_cantidad = (df["Cantidad_Vendida"] <= 0).fillna(False)
    n_cantidad = int(mask_cantidad.sum())
    valores_neg = sorted(pd.to_numeric(
        crudo.loc[mask_cantidad, "Cantidad_Vendida"], errors="coerce").unique())
    if n_cantidad:
        log.excluir("transacciones_cantidad_invalida", crudo.loc[mask_cantidad])
    df.loc[mask_cantidad, "Cantidad_Vendida"] = np.nan
    log.agregar(
        dataset=ds, columna="Cantidad_Vendida",
        accion="Reclasificación de centinela a nulo",
        criterio="Cantidad vendida debe ser estrictamente positiva",
        justificacion=(
            "El único valor negativo es -5 y aparece exactamente 100 veces: "
            "un patrón de centinela inyectado, no de devoluciones reales (que "
            "producirían magnitudes variadas)."),
        filas_afectadas=n_cantidad, valor_aplicado="nulo",
        evidencia=f"valores negativos observados: {valores_neg}",
    )
    _imputar_cantidad_por_sku(df, mask_cantidad, ds, log)

    # --- Tiempo de entrega: centinela 999 --------------------------------
    df["Tiempo_Entrega_Real"] = pd.to_numeric(df["Tiempo_Entrega_Real"],
                                              errors="coerce")
    mask_999 = (df["Tiempo_Entrega_Real"]
                > config.MAX_DIAS_ENTREGA_PLAUSIBLE).fillna(False)
    n_999 = int(mask_999.sum())
    curtosis_antes = float(df["Tiempo_Entrega_Real"].kurtosis())
    if n_999:
        log.excluir("transacciones_entrega_999", crudo.loc[mask_999])
    df["Entrega_Codigo_Error"] = mask_999
    df.loc[mask_999, "Tiempo_Entrega_Real"] = np.nan
    curtosis_despues = float(df["Tiempo_Entrega_Real"].kurtosis())
    log.agregar(
        dataset=ds, columna="Tiempo_Entrega_Real",
        accion="Reclasificación de centinela a nulo",
        criterio=f"Valores > {config.MAX_DIAS_ENTREGA_PLAUSIBLE} días",
        justificacion=(
            "999 es el único valor por encima de 100 días y aparece exactamente "
            "50 veces: es un código de error del sistema logístico, no una "
            "entrega lenta real. La prueba es distribucional: al retirarlo, la "
            "curtosis colapsa de un valor extremo a la de una distribución "
            "uniforme, revelando que el resto de la columna es homogéneo entre "
            "1 y 29 días. Tratarlo como dato real habría inflado el tiempo "
            "medio de entrega en un 33 %."),
        filas_afectadas=n_999, valor_aplicado="nulo",
        evidencia=(f"curtosis {curtosis_antes:.2f} → {curtosis_despues:.2f} "
                   f"al retirar el centinela"),
    )
    _imputar_numerica(
        df, "Tiempo_Entrega_Real", ds, log,
        justificacion=(
            "Depurado el centinela, los tiempos de entrega resultan simétricos "
            "y uniformes entre 1 y 29 días, por lo que la regla selecciona la "
            "media. La media (14,96) y la mediana (15,00) coinciden hasta la "
            "primera décima, de modo que la elección es indiferente en la "
            "práctica: esa coincidencia es en sí la prueba de simetría. Sobre "
            "el dato crudo, en cambio, la media era 19,88 porque el centinela "
            "999 la inflaba un 33 %."),
    )

    # --- Costo de envío ---------------------------------------------------
    df["Costo_Envio"] = pd.to_numeric(df["Costo_Envio"], errors="coerce")
    _imputar_numerica(
        df, "Costo_Envio", ds, log,
        justificacion=(
            "El costo de envío se distribuye de forma simétrica y casi uniforme "
            "entre USD 5 y USD 100, sin outliers según el criterio de Tukey. "
            "En ausencia de cola, la media es el estimador de tendencia central "
            "más eficiente y preserva el total agregado de gasto logístico, que "
            "es lo que importa para el cálculo de margen neto."),
    )

    df["Precio_Venta_Final"] = pd.to_numeric(df["Precio_Venta_Final"],
                                             errors="coerce")

    # --- Ciudad destino ---------------------------------------------------
    df = _normalizar_ciudad(df, log, ds)

    # --- Estado de envío --------------------------------------------------
    df["Estado_Envio"] = _a_nulo_centinelas(df["Estado_Envio"])
    faltantes_estado = int(df["Estado_Envio"].isna().sum())
    entropia_estado = _entropia_normalizada(df["Estado_Envio"])
    log.agregar(
        dataset=ds, columna="Estado_Envio", accion="NO imputar (nulo deliberado)",
        criterio=f"Entropía normalizada > {UMBRAL_ENTROPIA_UNIFORME}",
        justificacion=(
            "Los cinco estados de envío se reparten casi por igual, así que la "
            "moda no tiene poder explicativo. Imputarla concentraría un 16,8 % "
            "de masa artificial en un solo estado y falsearía la tasa de envíos "
            "adversos, que es precisamente la métrica con la que se diagnostica "
            "el cuello de botella logístico."),
        filas_afectadas=faltantes_estado, valor_aplicado="se conserva como nulo",
        evidencia=f"entropía normalizada={entropia_estado:.4f} sobre "
                  f"{df['Estado_Envio'].nunique()} estados",
    )

    df["Canal_Venta"] = _a_nulo_centinelas(df["Canal_Venta"])
    return df, log


def _normalizar_ciudad(
    df: pd.DataFrame, log: RegistroLimpieza, dataset: str
) -> pd.DataFrame:
    """Unifica nombres de ciudad y separa el canal infiltrado en la geografía."""
    original = df["Ciudad_Destino"].astype("string").str.strip()
    clave = original.str.lower()

    mask_no_geo = clave.isin(config.VALORES_CIUDAD_NO_GEOGRAFICOS).fillna(False)
    df[config.COL_FLAG_SIN_GEO] = mask_no_geo

    normalizada = clave.map(config.MAPA_CIUDADES).astype("string")
    df["Ciudad_Destino"] = normalizada.mask(mask_no_geo)

    n_unificados = int(((original != df["Ciudad_Destino"]) & ~mask_no_geo
                        & df["Ciudad_Destino"].notna()).sum())
    log.agregar(
        dataset=dataset, columna="Ciudad_Destino",
        accion="Normalización con diccionario de mapeo",
        criterio="Mapeo de códigos IATA y variantes de caja a nombre canónico",
        justificacion=(
            "'MED' y 'Medellín' son la misma plaza registrada por sistemas "
            "distintos. Sin unificar, el filtro geográfico del sidebar "
            "ofrecería ocho opciones para cinco ciudades y partiría en dos la "
            "muestra de cada plaza, invalidando cualquier comparación regional "
            "de desempeño logístico."),
        filas_afectadas=n_unificados, valor_aplicado="8 variantes → 5 ciudades",
    )
    log.agregar(
        dataset=dataset, columna="Ciudad_Destino",
        accion="Anulación geográfica con bandera",
        criterio="'Ventas_Web' denota canal, no lugar",
        justificacion=(
            "'Ventas_Web' es una dimensión de canal infiltrada en una columna "
            "geográfica. Se anula la geografía y se marca la fila en lugar de "
            "eliminarla: así el ingreso permanece trazable al archivo original "
            "y el volumen de ventas sin geolocalización se convierte en un "
            "hallazgo de auditoría por derecho propio."),
        filas_afectadas=int(mask_no_geo.sum()),
        valor_aplicado=f"nulo + bandera {config.COL_FLAG_SIN_GEO}",
        evidencia=f"{100 * mask_no_geo.mean():.1f}% de las transacciones "
                  f"quedan sin geolocalización",
    )
    return df


# --------------------------------------------------------------------------
# Limpieza: Feedback
# --------------------------------------------------------------------------


def limpiar_feedback(
    crudo: pd.DataFrame, politica_duplicados: str = "conservar",
) -> tuple[pd.DataFrame, RegistroLimpieza]:
    """Cura la voz del cliente.

    Args:
        crudo: DataFrame de feedback tal como sale de ``ingest``.
        politica_duplicados: ``'conservar'`` repara la llave colisionada sin
            perder registros (recomendado). ``'eliminar'`` descarta las
            repeticiones de ``Feedback_ID`` conservando la más completa, que es
            la lectura literal del enunciado.

    Returns:
        Tupla (DataFrame limpio y tipado, bitácora de decisiones).

    Raises:
        ValueError: Si la política de duplicados no es reconocida.
    """
    if politica_duplicados not in {"conservar", "eliminar"}:
        raise ValueError(
            f"Política de duplicados no reconocida: '{politica_duplicados}'. "
            "Use 'conservar' o 'eliminar'.")

    df = crudo.copy()
    log = RegistroLimpieza()
    ds = "feedback"

    df = _resolver_llave_feedback(df, politica_duplicados, log, ds)
    df = _marcar_feedback_confiable(df, ds, log)

    # --- Ratings fuera de escala -----------------------------------------
    for columna in ("Rating_Producto", "Rating_Logistica"):
        df[columna] = pd.to_numeric(df[columna], errors="coerce")
        mask = (~df[columna].between(*config.RANGO_RATING)
                & df[columna].notna())
        n = int(mask.sum())
        fuera_escala = sorted(df.loc[mask, columna].unique().tolist())
        if n:
            log.excluir(f"feedback_{columna.lower()}_fuera_escala",
                        df.loc[mask])
        df[f"{columna}_Fuera_Escala"] = mask
        df[columna] = df[columna].astype("Float64").mask(mask)
        if n:
            log.agregar(
                dataset=ds, columna=columna,
                accion="Anulación de valores fuera de escala",
                criterio=f"Fuera de la escala declarada {config.RANGO_RATING}",
                justificacion=(
                    "El valor 99 es un centinela de 'sin respuesta' de la "
                    "plataforma de encuestas, no una calificación."),
                filas_afectadas=n, valor_aplicado="nulo",
                evidencia=f"valores fuera de escala observados: "
                          f"{fuera_escala} ({100 * n / len(df):.2f}% de las filas)",
            )

        mediana = float(df[columna].median())
        df[sufijo_imputado(columna)] = mask
        df[columna] = df[columna].fillna(mediana)
        if n:
            log.agregar(
                dataset=ds, columna=columna, accion="Imputación por mediana",
                criterio="Mediana de las respuestas válidas (escala ordinal)",
                justificacion=(
                    f"{columna} es una calificación ordinal de "
                    f"{config.RANGO_RATING[0]} a {config.RANGO_RATING[1]}, no "
                    "una magnitud continua: la mediana es el estadístico de "
                    "tendencia central correcto para datos ordinales, porque "
                    "no asume que la distancia entre 'Malo' y 'Regular' sea "
                    "igual a la distancia entre 'Bueno' y 'Excelente', como sí "
                    "lo haría la media."),
                filas_afectadas=n, valor_aplicado=f"{mediana:.0f}",
                evidencia=(f"mediana de las {len(df) - n} respuestas válidas "
                          f"= {mediana:.0f}; marcados en "
                          f"{sufijo_imputado(columna)}"),
            )

    # --- Edad del cliente -------------------------------------------------
    df["Edad_Cliente"] = pd.to_numeric(df["Edad_Cliente"], errors="coerce")
    mask_edad = (~df["Edad_Cliente"].between(*config.RANGO_EDAD_CLIENTE)
                 & df["Edad_Cliente"].notna())
    n_edad = int(mask_edad.sum())
    curtosis_antes = float(df["Edad_Cliente"].kurtosis())
    df.loc[mask_edad, "Edad_Cliente"] = np.nan
    curtosis_despues = float(df["Edad_Cliente"].kurtosis())
    log.agregar(
        dataset=ds, columna="Edad_Cliente", accion="Anulación de valores imposibles",
        criterio=f"Fuera del rango plausible {config.RANGO_EDAD_CLIENTE}",
        justificacion=(
            "Edades de hasta 195 años son imposibles. Igual que con el tiempo "
            "de entrega, la evidencia de que son inyectadas y no cola real es "
            "distribucional: al retirarlas la curtosis colapsa a la de una "
            "uniforme, dejando un rango coherente de 18 a 84 años."),
        filas_afectadas=n_edad, valor_aplicado="nulo",
        evidencia=f"curtosis {curtosis_antes:.2f} → {curtosis_despues:.2f}",
    )
    _imputar_numerica(
        df, "Edad_Cliente", ds, log,
        justificacion=(
            "Depuradas las edades imposibles, la distribución es simétrica y "
            "uniforme entre 18 y 84 años, con media y mediana prácticamente "
            "idénticas. La coincidencia de ambos estadísticos es en sí la "
            "evidencia de simetría que respalda el uso de la media."),
    )

    # --- NPS: segmentación ------------------------------------------------
    df["Satisfaccion_NPS"] = pd.to_numeric(df["Satisfaccion_NPS"],
                                           errors="coerce")
    df[config.COL_SEGMENTO_NPS] = _segmentar_nps(df["Satisfaccion_NPS"])
    reparto = df[config.COL_SEGMENTO_NPS].value_counts(normalize=True)
    log.agregar(
        dataset=ds, columna="Satisfaccion_NPS",
        accion="Segmentación en categorías estándar",
        criterio="Detractor < 0 ; Pasivo 0-49 ; Promotor ≥ 50",
        justificacion=(
            "El dato llega como índice continuo -100 a +100 y no como la "
            "escala 0-10 canónica. Se conserva el valor crudo y se añade la "
            "segmentación estándar porque es el lenguaje que la junta "
            "directiva reconoce y porque define 'NPS bajo' con un umbral no "
            "arbitrario. Advertencia registrada en la auditoría: esta variable "
            "no correlaciona con ninguna otra del conjunto."),
        filas_afectadas=int(df["Satisfaccion_NPS"].notna().sum()),
        valor_aplicado=config.COL_SEGMENTO_NPS,
        evidencia="; ".join(f"{k}={100 * v:.1f}%" for k, v in reparto.items()),
    )

    # --- Ticket de soporte: codificación mixta ---------------------------
    original_ticket = df["Ticket_Soporte_Abierto"].astype("string").str.strip()
    df["Ticket_Soporte_Abierto"] = (
        original_ticket.str.lower().map(config.MAPA_BOOLEANOS).astype("boolean"))
    log.agregar(
        dataset=ds, columna="Ticket_Soporte_Abierto",
        accion="Unificación de codificación booleana",
        criterio="Mapeo de {Sí, No, 1, 0} a booleano",
        justificacion=(
            "La columna mezcla dos codificaciones de dos sistemas distintos: "
            "'Sí'/'No' y 1/0. Sin unificarlas, cualquier conteo de tickets "
            "contaría solo la mitad de los casos y subestimaría a la mitad la "
            "carga operativa de soporte."),
        filas_afectadas=len(df),
        valor_aplicado="booleano",
        evidencia=f"tasa de tickets unificada="
                  f"{100 * df['Ticket_Soporte_Abierto'].mean():.1f}%",
    )

    # --- Recomendación y comentario --------------------------------------
    original_recomienda = df["Recomienda_Marca"].copy()
    df["Recomienda_Marca"] = _normalizar_categorica(df["Recomienda_Marca"],
                                                    config.MAPA_RECOMIENDA)
    unificados = int((_a_nulo_centinelas(original_recomienda).str.strip()
                      != df["Recomienda_Marca"]).fillna(False).sum())
    log.agregar(
        dataset=ds, columna="Recomienda_Marca",
        accion="Normalización de variantes",
        criterio="Diccionario de mapeo sobre forma canónica en minúsculas",
        justificacion=(
            "'SI'/'NO' en mayúsculas y 'Maybe' en inglés son la misma "
            "pregunta de fidelidad respondida por sistemas distintos. "
            "'Maybe' se traduce a 'Indeciso' como una tercera categoría "
            "propia, no se fuerza hacia Sí o No: es una respuesta "
            "genuinamente distinta a una omisión, y forzarla perdería la "
            "diferencia entre 'no sabe' y 'no responde' que la pregunta de "
            "fidelidad necesita distinguir."),
        filas_afectadas=unificados, valor_aplicado="4 variantes → 3 categorías",
    )
    comentario = _a_nulo_centinelas(df["Comentario_Texto"]).str.lower()
    df["Sentimiento"] = comentario.map(config.MAPA_SENTIMIENTO).astype("string")
    df["Causa_Queja"] = comentario.map(config.MAPA_CAUSA_QUEJA).astype("string")
    df["Comentario_Texto"] = _a_nulo_centinelas(df["Comentario_Texto"])
    log.agregar(
        dataset=ds, columna="Comentario_Texto",
        accion="Derivación de sentimiento y causa raíz",
        criterio="Mapeo del conjunto cerrado de comentarios",
        justificacion=(
            "Comentario_Texto no es texto libre sino un conjunto cerrado de "
            "siete frases enlatadas, por lo que no requiere procesamiento de "
            "lenguaje natural. Se derivan dos ejes: sentimiento y causa raíz "
            "(Calidad / Logística / Precio-Valor), que es lo que permite "
            "resolver si la insatisfacción de una categoría obedece a mala "
            "calidad o a sobrecosto."),
        filas_afectadas=int(df["Sentimiento"].notna().sum()),
        valor_aplicado="columnas Sentimiento y Causa_Queja",
        evidencia=f"{int(df['Comentario_Texto'].isna().sum())} comentarios "
                  f"ausentes tras depurar centinelas",
    )
    return df, log


def _segmentar_nps(serie: pd.Series) -> pd.Series:
    """Clasifica el índice NPS en Detractor / Pasivo / Promotor."""
    condiciones = [serie < 0, serie < 50, serie >= 50]
    etiquetas = ["Detractor", "Pasivo", "Promotor"]
    resultado = np.select(condiciones, etiquetas, default=None)
    return pd.Series(resultado, index=serie.index, dtype="string")


def _marcar_feedback_confiable(
    df: pd.DataFrame, dataset: str, log: RegistroLimpieza
) -> pd.DataFrame:
    """Marca las opiniones de un ``Transaccion_ID`` con más de un ``Feedback_ID``.

    767 transacciones reciben entre 2 y 4 opiniones de clientes distintos
    (ver ``integration.agregar_feedback_a_transaccion``). No se puede saber
    cuál de esas filas es "la" opinión real de esa venta, así que ni se
    elimina ninguna (perdería información) ni se promedia en silencio
    (mezclaría clientes distintos bajo una sola venta sin dejar rastro). Se
    marca cada fila del grupo con ``Feedback_Confiable = False`` para que el
    análisis aguas abajo —el diagnóstico de fidelidad— pueda excluir o tratar
    con cautela esas ventas en vez de heredar un sesgo invisible.
    """
    n_opiniones = df.groupby("Transaccion_ID")["Transaccion_ID"].transform("size")
    conflictivo = n_opiniones > 1
    df["Feedback_Confiable"] = ~conflictivo

    n_filas = int(conflictivo.sum())
    n_transacciones = int(df.loc[conflictivo, "Transaccion_ID"].nunique())
    log.agregar(
        dataset=dataset, columna="Feedback_Confiable",
        accion="Marcado de grupos conflictivos (sin eliminar ni promediar)",
        criterio="Transaccion_ID con 2 o más Feedback_ID distintos",
        justificacion=(
            "No se puede saber cuál de las 2-4 filas es 'la real', así que "
            "eliminarlas arbitrariamente perdería información y "
            "promediarlas sin avisar mezclaría opiniones de clientes "
            "distintos bajo una sola venta. La bandera permite que el "
            "diagnóstico de fidelidad excluya o trate con cautela estas "
            "ventas, en vez de heredar un sesgo invisible."),
        filas_afectadas=n_filas, valor_aplicado="Feedback_Confiable = False",
        evidencia=(
            f"{n_transacciones} transacciones con 2 a "
            f"{int(n_opiniones.max())} opiniones concentran {n_filas} de las "
            f"{len(df)} filas de feedback"),
    )
    return df


def _resolver_llave_feedback(
    df: pd.DataFrame, politica: str, log: RegistroLimpieza, ds: str
) -> pd.DataFrame:
    """Trata la colisión de Feedback_ID según la política elegida.

    Hallazgo que motiva el diseño: el dataset NO contiene duplicados reales.
    No hay una sola fila repetida, ni siquiera ignorando el identificador.
    Los ``Feedback_ID`` que se repiten apuntan a transacciones distintas, con
    edades y calificaciones distintas: son clientes diferentes con una llave
    surrogate mal generada.
    """
    columnas_contenido = [c for c in df.columns if c != "Feedback_ID"]
    dup_exactos = int(df.duplicated().sum())
    dup_sin_llave = int(df.duplicated(subset=columnas_contenido).sum())
    colisiones = int(df.duplicated(subset=["Feedback_ID"]).sum())
    ids_colisionados = int(
        df["Feedback_ID"][df["Feedback_ID"].duplicated(keep=False)].nunique())

    log.agregar(
        dataset=ds, columna="Feedback_ID",
        accion="Diagnóstico de duplicación",
        criterio="Comparación de filas completas y de contenido sin la llave",
        justificacion=(
            "No existe un solo duplicado real en este activo. Las repeticiones "
            "de Feedback_ID corresponden a opiniones de clientes distintos "
            "sobre transacciones distintas: una colisión de llave surrogate, no "
            "una duplicación de registros. Eliminarlas por identificador "
            "destruiría opiniones legítimas y sesgaría todo el análisis de "
            "cliente."),
        filas_afectadas=colisiones,
        valor_aplicado=f"política='{politica}'",
        evidencia=(f"{dup_exactos} filas idénticas; {dup_sin_llave} idénticas "
                   f"ignorando la llave; {ids_colisionados} IDs colisionados "
                   f"en {colisiones + ids_colisionados} filas"),
    )

    if politica == "eliminar":
        # Lectura literal del enunciado: se conserva la fila más completa de
        # cada grupo, para que la pérdida de información sea la mínima posible.
        centinelas = {c.strip().lower() for c in config.CENTINELAS_NULOS
                      if c.strip()}
        incompletitud = df.apply(
            lambda col: col.astype("string").str.strip().str.lower()
            .isin(centinelas), axis=0).sum(axis=1)
        orden = df.assign(_incompletitud=incompletitud).sort_values(
            "_incompletitud", kind="stable")
        conservadas = orden.drop_duplicates(subset=["Feedback_ID"], keep="first")
        eliminadas = df.loc[~df.index.isin(conservadas.index)]
        log.excluir("feedback_id_colisionado_eliminado", eliminadas)
        log.agregar(
            dataset=ds, columna="Feedback_ID",
            accion="Eliminación de repeticiones de llave",
            criterio="Se conserva la fila con menos campos ausentes",
            justificacion=(
                "Política literal del enunciado. El desempate por completitud "
                "evita descartar información al azar, pero se advierte que "
                "estas filas no son duplicados y su eliminación reduce la "
                "muestra de opiniones reales."),
            filas_afectadas=len(eliminadas), valor_aplicado="filas eliminadas",
        )
        return conservadas.drop(columns="_incompletitud").sort_index()

    # Política recomendada: reparar la llave sin perder registros.
    df = df.copy()
    df["Feedback_ID_Colisionado"] = df["Feedback_ID"].duplicated(keep=False)
    df["Feedback_UID"] = (
        df["Feedback_ID"] + "-" +
        df.groupby("Feedback_ID").cumcount().add(1).astype(str))
    log.agregar(
        dataset=ds, columna="Feedback_UID",
        accion="Reparación de llave primaria",
        criterio="Sufijo secuencial por grupo de Feedback_ID",
        justificacion=(
            "Se genera un identificador único derivado en lugar de eliminar "
            "filas. Conserva el 100 % de las opiniones y deja el problema de "
            "integridad visible y auditable en la bandera "
            "Feedback_ID_Colisionado."),
        filas_afectadas=colisiones, valor_aplicado="Feedback_UID",
    )
    return df


# --------------------------------------------------------------------------
# Orquestación del pipeline
# --------------------------------------------------------------------------


@dataclass
class ResultadoLimpieza:
    """Salida completa de la Fase 1, lista para la UI y el reporte."""

    crudos: dict[str, pd.DataFrame]
    limpios: dict[str, pd.DataFrame]
    registro: RegistroLimpieza
    scores_antes: dict
    scores_despues: dict

    def comparativo(self) -> pd.DataFrame:
        """Tabla antes vs después por dataset."""
        from src.audit import comparar_scores
        return pd.DataFrame([
            comparar_scores(self.scores_antes[n], self.scores_despues[n])
            for n in self.crudos
        ])

    def reporte_dict(self) -> dict:
        """Reporte de limpieza serializable a JSON."""
        return {
            "fecha_ejecucion": str(config.fecha_corte()),
            "resumen_por_dataset": self.comparativo().to_dict("records"),
            "decisiones": [a.a_dict() for a in self.registro.acciones],
            "registros_excluidos": {
                etiqueta: len(frame)
                for etiqueta, frame in self.registro.excluidos.items()
            },
        }

    def reporte_csv(self) -> str:
        """Bitácora de decisiones en CSV, para el botón de descarga."""
        return self.registro.a_dataframe().to_csv(index=False,
                                                  encoding="utf-8")

    def comparativo_csv(self) -> str:
        """Tabla antes/después en CSV, para el botón de descarga."""
        return self.comparativo().to_csv(index=False, encoding="utf-8")


def ejecutar_pipeline(
    crudos: dict[str, pd.DataFrame] | None = None,
    politica_duplicados: str = "conservar",
) -> ResultadoLimpieza:
    """Ejecuta la auditoría, la limpieza y la re-auditoría de los tres activos.

    Args:
        crudos: Datos ya ingeridos. Si es None, se cargan desde disco.
        politica_duplicados: Ver ``limpiar_feedback``.

    Returns:
        ResultadoLimpieza con crudos, limpios, bitácora y ambos Health Scores.

    Raises:
        ErrorIngesta: Si falla la carga de algún archivo fuente.
    """
    from src import audit, ingest

    if crudos is None:
        crudos = ingest.cargar_todos_crudos()

    limpiadores: dict[str, Callable] = {
        "inventario": limpiar_inventario,
        "transacciones": limpiar_transacciones,
        "feedback": lambda d: limpiar_feedback(d, politica_duplicados),
    }

    limpios, registro = {}, RegistroLimpieza()
    scores_antes, scores_despues = {}, {}

    for nombre, crudo in crudos.items():
        scores_antes[nombre] = audit.calcular_health_score(crudo, nombre, "antes")
        try:
            limpio, log = limpiadores[nombre](crudo)
        except (KeyError, ValueError, TypeError) as exc:
            logger.error("Falló la limpieza de '%s': %s", nombre, exc)
            raise
        limpios[nombre] = limpio
        registro.fusionar(log)
        scores_despues[nombre] = audit.calcular_health_score(
            limpio, nombre, "despues")

    return ResultadoLimpieza(
        crudos=crudos, limpios=limpios, registro=registro,
        scores_antes=scores_antes, scores_despues=scores_despues,
    )
