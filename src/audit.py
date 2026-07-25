"""Auditoría de calidad de datos: Health Score y métricas de transparencia.

Este módulo mide, no transforma. Se ejecuta dos veces sobre cada activo
—antes y después de la limpieza— para producir la comparación que exige el
módulo de transparencia del dashboard.

El Health Score agrega cuatro dimensiones en un índice 0-100:

    completitud   1 - (celdas ausentes / celdas totales)
    validez       1 - (celdas que violan una regla de negocio / celdas sujetas)
    unicidad      1 - (filas duplicadas / filas totales)
    consistencia  1 - (valores categóricos no canónicos / valores categóricos)

Nota metodológica importante: la completitud NO mejora artificialmente cuando
se decide no imputar. Si una columna queda con nulos porque imputarla habría
fabricado señal, el score lo refleja y la justificación queda en el registro
de limpieza. Un Health Score de 100 % obtenido rellenando huecos con la moda
sería una mentira estadística.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import config

logger = logging.getLogger(__name__)

_CENTINELAS = {c.strip().lower() for c in config.CENTINELAS_NULOS if c.strip()}


# --------------------------------------------------------------------------
# Estructuras de resultado
# --------------------------------------------------------------------------


@dataclass
class ResultadoDimension:
    """Puntaje de una dimensión de calidad y su evidencia."""

    nombre: str
    score: float          # 0.0 - 1.0
    afectados: int
    evaluados: int
    detalle: dict = field(default_factory=dict)

    @property
    def pct(self) -> float:
        """Puntaje en escala 0-100."""
        return round(100 * self.score, 2)


@dataclass
class HealthScore:
    """Health Score compuesto de un dataset en un momento dado."""

    dataset: str
    momento: str          # 'antes' | 'despues'
    filas: int
    columnas: int
    dimensiones: dict[str, ResultadoDimension]

    @property
    def total(self) -> float:
        """Índice 0-100 ponderado según config.PESOS_HEALTH_SCORE."""
        acumulado = sum(
            self.dimensiones[nombre].score * peso
            for nombre, peso in config.PESOS_HEALTH_SCORE.items()
            if nombre in self.dimensiones
        )
        return round(100 * acumulado, 2)

    def a_dict(self) -> dict:
        """Serializa el score para el reporte descargable."""
        return {
            "dataset": self.dataset,
            "momento": self.momento,
            "filas": self.filas,
            "columnas": self.columnas,
            "health_score": self.total,
            **{
                f"{nombre}_pct": dim.pct
                for nombre, dim in self.dimensiones.items()
            },
        }


# --------------------------------------------------------------------------
# Utilidades de medición
# --------------------------------------------------------------------------


def _serie_numerica(serie: pd.Series) -> pd.Series:
    """Coerciona a numérico tolerando datos crudos en texto."""
    if pd.api.types.is_numeric_dtype(serie):
        return serie
    return pd.to_numeric(serie, errors="coerce")


def _mascara_ausente(serie: pd.Series) -> pd.Series:
    """Marca ausencias reales, incluidos los centinelas de texto.

    En los datos crudos la ausencia viene disfrazada de valor ('???', 'nan',
    'N/A', '---'). Contar solo ``isna()`` subestimaría la nulidad real y haría
    ver el "antes" mejor de lo que es.
    """
    if pd.api.types.is_numeric_dtype(serie):
        return serie.isna()
    texto = serie.astype("string").str.strip().str.lower()
    return serie.isna() | texto.isin(_CENTINELAS) | (texto == "")


def detectar_outliers_iqr(
    serie: pd.Series, factor: float = config.FACTOR_IQR
) -> tuple[pd.Series, float, float]:
    """Detecta outliers por el criterio de Tukey (rango intercuartílico).

    Args:
        serie: Serie numérica (o coercionable).
        factor: Multiplicador del IQR. 1.5 es el valor clásico de Tukey.

    Returns:
        Tupla (máscara booleana de outliers, límite inferior, límite superior).
        Si la serie no tiene datos suficientes, devuelve máscara vacía y NaN.
    """
    valores = _serie_numerica(serie)
    if valores.notna().sum() < 4:
        return pd.Series(False, index=serie.index), np.nan, np.nan

    q1, q3 = valores.quantile([0.25, 0.75])
    iqr = q3 - q1
    inferior, superior = q1 - factor * iqr, q3 + factor * iqr
    return ((valores < inferior) | (valores > superior)).fillna(False), \
        float(inferior), float(superior)


def perfil_nulidad(df: pd.DataFrame) -> pd.DataFrame:
    """Porcentaje de ausencia real por columna.

    Returns:
        DataFrame con columnas: columna, ausentes, pct_ausentes.
    """
    filas = []
    for col in df.columns:
        ausentes = int(_mascara_ausente(df[col]).sum())
        filas.append({
            "columna": col,
            "ausentes": ausentes,
            "pct_ausentes": round(100 * ausentes / len(df), 2) if len(df) else 0.0,
        })
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------
# Reglas de validez por dataset
# --------------------------------------------------------------------------

# Cada regla declara: columna, predicado de VIOLACIÓN y por qué es inválido.
# El predicado recibe la serie ya coercionada a numérico cuando aplica.

REGLAS_VALIDEZ: dict[str, list[tuple]] = {
    "inventario": [
        ("Stock_Actual", lambda s: _serie_numerica(s) < 0,
         "Existencias negativas son contablemente imposibles"),
        ("Costo_Unitario_USD", lambda s: _serie_numerica(s) < 1,
         "Un costo unitario bajo USD 1 en electrónica es error de captura"),
        ("Costo_Unitario_USD",
         lambda s: detectar_outliers_iqr(s)[0],
         "Costo fuera del rango intercuartílico de Tukey"),
        ("Lead_Time_Dias", lambda s: pd.to_numeric(s, errors="coerce").isna()
         & ~_mascara_ausente(s),
         "Lead time no numérico ('25-30 días', 'Inmediato')"),
    ],
    "transacciones": [
        ("Cantidad_Vendida", lambda s: _serie_numerica(s) <= 0,
         "Cantidad vendida nula o negativa"),
        ("Tiempo_Entrega_Real",
         lambda s: _serie_numerica(s) > config.MAX_DIAS_ENTREGA_PLAUSIBLE,
         f"Entrega > {config.MAX_DIAS_ENTREGA_PLAUSIBLE} días: código de error"),
        ("Precio_Venta_Final", lambda s: _serie_numerica(s) <= 0,
         "Precio de venta nulo o negativo"),
        ("Fecha_Venta", lambda s: _fecha_posterior_a_corte(s),
         "Venta con fecha posterior al momento de ejecución del análisis"),
        ("Ciudad_Destino", lambda s: _es_ciudad_no_geografica(s),
         "Valor de canal ('Ventas_Web') en una columna geográfica"),
    ],
    "feedback": [
        ("Rating_Producto",
         lambda s: ~_serie_numerica(s).between(*config.RANGO_RATING)
         & _serie_numerica(s).notna(),
         f"Rating fuera de la escala {config.RANGO_RATING}"),
        ("Rating_Logistica",
         lambda s: ~_serie_numerica(s).between(*config.RANGO_RATING)
         & _serie_numerica(s).notna(),
         f"Rating fuera de la escala {config.RANGO_RATING}"),
        ("Edad_Cliente",
         lambda s: ~_serie_numerica(s).between(*config.RANGO_EDAD_CLIENTE)
         & _serie_numerica(s).notna(),
         f"Edad fuera del rango plausible {config.RANGO_EDAD_CLIENTE}"),
        ("Satisfaccion_NPS",
         lambda s: ~_serie_numerica(s).between(*config.RANGO_NPS)
         & _serie_numerica(s).notna(),
         f"NPS fuera del rango {config.RANGO_NPS}"),
    ],
}


def _fecha_posterior_a_corte(serie: pd.Series) -> pd.Series:
    """Marca fechas de venta posteriores al momento de ejecución."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        fechas = serie
    else:
        fechas = pd.to_datetime(
            serie, format=config.FORMATO_FECHA_TRANSACCIONES, errors="coerce"
        )
    return (fechas > pd.Timestamp(config.fecha_corte())).fillna(False)


def _es_ciudad_no_geografica(serie: pd.Series) -> pd.Series:
    """Marca valores de Ciudad_Destino que no denotan un lugar."""
    texto = serie.astype("string").str.strip().str.lower()
    return texto.isin(config.VALORES_CIUDAD_NO_GEOGRAFICOS).fillna(False)


# --------------------------------------------------------------------------
# Columnas categóricas sujetas a control de consistencia
# --------------------------------------------------------------------------

CATEGORICAS_NORMALIZABLES: dict[str, dict[str, dict]] = {
    "inventario": {
        "Categoria": config.MAPA_CATEGORIAS,
        "Bodega_Origen": config.MAPA_BODEGAS,
    },
    "transacciones": {
        "Ciudad_Destino": config.MAPA_CIUDADES,
    },
    "feedback": {
        "Recomienda_Marca": config.MAPA_RECOMIENDA,
        "Ticket_Soporte_Abierto": config.MAPA_BOOLEANOS,
    },
}


def _evaluar_completitud(df: pd.DataFrame) -> ResultadoDimension:
    """Mide la ausencia real de datos sobre el total de celdas."""
    total = df.size
    ausentes = int(sum(_mascara_ausente(df[c]).sum() for c in df.columns))
    perfil = perfil_nulidad(df)
    peores = perfil.nlargest(5, "pct_ausentes")
    return ResultadoDimension(
        nombre="completitud",
        score=1 - (ausentes / total) if total else 1.0,
        afectados=ausentes,
        evaluados=total,
        detalle={"peores_columnas": peores.to_dict("records")},
    )


def _evaluar_validez(df: pd.DataFrame, nombre: str) -> ResultadoDimension:
    """Mide violaciones a las reglas de negocio declaradas por dataset."""
    violaciones, evaluados, detalle = 0, 0, []

    for columna, predicado, descripcion in REGLAS_VALIDEZ.get(nombre, []):
        if columna not in df.columns:
            continue
        try:
            mascara = predicado(df[columna]).fillna(False)
        except (TypeError, ValueError) as exc:
            logger.warning("Regla no evaluable en %s.%s: %s",
                           nombre, columna, exc)
            continue

        n = int(mascara.sum())
        violaciones += n
        evaluados += len(df)
        if n:
            detalle.append({
                "columna": columna,
                "regla": descripcion,
                "violaciones": n,
                "pct": round(100 * n / len(df), 2),
            })

    return ResultadoDimension(
        nombre="validez",
        score=1 - (violaciones / evaluados) if evaluados else 1.0,
        afectados=violaciones,
        evaluados=evaluados,
        detalle={"reglas_violadas": detalle},
    )


def _evaluar_unicidad(df: pd.DataFrame, nombre: str) -> ResultadoDimension:
    """Mide duplicación real de registros y colisiones de llave.

    Se distinguen dos patologías que suelen confundirse:

    * **Duplicado real**: la fila entera se repite. Es basura y se elimina.
    * **Colisión de llave**: el identificador se repite pero el contenido
      difiere. NO es un duplicado: son registros distintos con una llave
      surrogate mal generada. Eliminarlos destruye información.

    Solo el duplicado real penaliza el score; la colisión se reporta aparte
    porque su remedio es reparar la llave, no borrar filas.
    """
    llave = df.columns[0]
    dup_exactos = int(df.duplicated().sum())

    columnas_contenido = [c for c in df.columns if c != llave]
    dup_contenido = int(df.duplicated(subset=columnas_contenido).sum()) \
        if columnas_contenido else 0
    colisiones_llave = int(df.duplicated(subset=[llave]).sum())

    return ResultadoDimension(
        nombre="unicidad",
        score=1 - (dup_exactos / len(df)) if len(df) else 1.0,
        afectados=dup_exactos,
        evaluados=len(df),
        detalle={
            "llave_evaluada": llave,
            "duplicados_exactos": dup_exactos,
            "duplicados_ignorando_llave": dup_contenido,
            "colisiones_de_llave": colisiones_llave,
        },
    )


def _evaluar_consistencia(df: pd.DataFrame, nombre: str) -> ResultadoDimension:
    """Mide cuántos valores categóricos no están en su forma canónica."""
    no_canonicos, evaluados, detalle = 0, 0, []

    for columna, mapa in CATEGORICAS_NORMALIZABLES.get(nombre, {}).items():
        if columna not in df.columns:
            continue
        # Esta dimensión mide normalización *textual*. Una columna ya tipada
        # (booleana, numérica, fecha) es canónica por construcción: no puede
        # albergar variantes de caja ni codificaciones mixtas.
        if not pd.api.types.is_string_dtype(df[columna]):
            evaluados += int((~_mascara_ausente(df[columna])).sum())
            continue
        serie = df[columna].astype("string")
        presentes = ~_mascara_ausente(df[columna])
        clave = serie.str.strip().str.lower()
        canonico = clave.map(mapa)

        # No canónico = existe forma canónica y difiere del valor original.
        difiere = (canonico.notna() & (canonico != serie.str.strip())
                   & presentes).fillna(False)
        n = int(difiere.sum())
        no_canonicos += n
        evaluados += int(presentes.sum())
        if n:
            variantes = serie[difiere].value_counts().head(6).to_dict()
            detalle.append({
                "columna": columna,
                "valores_no_canonicos": n,
                "variantes": variantes,
            })

    return ResultadoDimension(
        nombre="consistencia",
        score=1 - (no_canonicos / evaluados) if evaluados else 1.0,
        afectados=no_canonicos,
        evaluados=evaluados,
        detalle={"columnas_inconsistentes": detalle},
    )


def calcular_health_score(
    df: pd.DataFrame, nombre: str, momento: str,
    solo_esquema_original: bool = True,
) -> HealthScore:
    """Calcula el Health Score compuesto de un dataset.

    Args:
        df: DataFrame a evaluar (crudo en texto o ya limpio y tipado).
        nombre: 'inventario', 'transacciones' o 'feedback'.
        momento: 'antes' o 'despues', solo como etiqueta del resultado.
        solo_esquema_original: Restringe la medición a las columnas del
            esquema fuente. Es lo correcto por defecto: la limpieza agrega
            columnas derivadas (banderas, segmentos) y puntuar sobre conjuntos
            de columnas distintos haría incomparables el antes y el después.
            Una derivada que hereda la nulidad de su origen contaría dos veces
            la misma ausencia y penalizaría una limpieza que no empeoró nada.

    Returns:
        HealthScore con las cuatro dimensiones y su evidencia.

    Raises:
        ValueError: Si el DataFrame está vacío.
    """
    if df.empty:
        raise ValueError(f"No se puede auditar un dataset vacío: '{nombre}'")

    if solo_esquema_original:
        columnas = [c for c in config.ESQUEMAS[nombre] if c in df.columns]
        df = df[columnas]

    dimensiones = {
        "completitud": _evaluar_completitud(df),
        "validez": _evaluar_validez(df, nombre),
        "unicidad": _evaluar_unicidad(df, nombre),
        "consistencia": _evaluar_consistencia(df, nombre),
    }
    score = HealthScore(
        dataset=nombre,
        momento=momento,
        filas=len(df),
        columnas=df.shape[1],
        dimensiones=dimensiones,
    )
    logger.info("Health Score %s (%s): %.2f", nombre, momento, score.total)
    return score


def comparar_scores(
    antes: HealthScore, despues: HealthScore
) -> dict[str, float]:
    """Construye la fila 'antes vs después' de la pestaña de Transparencia."""
    fila = {
        "dataset": antes.dataset,
        "filas_antes": antes.filas,
        "filas_despues": despues.filas,
        "filas_eliminadas": antes.filas - despues.filas,
        "health_score_antes": antes.total,
        "health_score_despues": despues.total,
        "mejora_pp": round(despues.total - antes.total, 2),
    }
    for nombre in config.PESOS_HEALTH_SCORE:
        fila[f"{nombre}_antes"] = antes.dimensiones[nombre].pct
        fila[f"{nombre}_despues"] = despues.dimensiones[nombre].pct
    return fila
