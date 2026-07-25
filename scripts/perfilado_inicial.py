"""Perfilado forense de los datos crudos (línea base de la auditoría).

Genera la fotografía "ANTES" del estado de los tres activos de información:
centinelas de nulos, cardinalidad de categóricas, viabilidad de coerción
numérica, integridad referencial y duplicados.

Este reporte es la evidencia que sustenta las reglas de limpieza de la Fase 1
y alimenta la columna "Antes" de la pestaña de Transparencia del dashboard.

Uso:
    python -m scripts.perfilado_inicial
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src import config, ingest  # noqa: E402

LIMITE_CARDINALIDAD = 20
SEPARADOR = "=" * 78


def _perfilar_columna(serie: pd.Series) -> dict:
    """Calcula métricas forenses de una columna cruda (texto)."""
    total = len(serie)
    vacios = (serie.str.strip() == "").sum()
    centinelas = serie.str.strip().str.lower().isin(
        [c.lower() for c in config.CENTINELAS_NULOS if c]
    ).sum()
    numericos = pd.to_numeric(serie, errors="coerce")
    no_numericos = numericos.isna().sum()

    return {
        "distintos": serie.nunique(),
        "vacios": int(vacios),
        "centinelas": int(centinelas),
        "pct_ausencia_real": round(100 * (vacios + centinelas) / total, 2),
        "no_coercibles_a_numero": int(no_numericos),
    }


def _reporte_dataset(nombre: str, df: pd.DataFrame, salida: list[str]) -> None:
    """Escribe el perfilado completo de un dataset en el buffer de salida."""
    salida.append(f"\n## Dataset: `{nombre}` — {df.shape[0]:,} filas x "
                  f"{df.shape[1]} columnas\n")
    salida.append("| Columna | Distintos | Vacíos | Centinelas | % ausencia real "
                  "| No numéricos |")
    salida.append("|---|---:|---:|---:|---:|---:|")

    for col in df.columns:
        m = _perfilar_columna(df[col])
        salida.append(
            f"| `{col}` | {m['distintos']:,} | {m['vacios']:,} | "
            f"{m['centinelas']:,} | {m['pct_ausencia_real']}% | "
            f"{m['no_coercibles_a_numero']:,} |"
        )

    salida.append("\n### Valores distintos en columnas de baja cardinalidad\n")
    for col in df.columns:
        distintos = df[col].nunique()
        if distintos <= LIMITE_CARDINALIDAD:
            conteo = df[col].value_counts(dropna=False)
            detalle = ", ".join(
                f"`{repr(idx)}`={val:,}" for idx, val in conteo.items()
            )
            salida.append(f"- **{col}** ({distintos} valores): {detalle}")

    salida.append("\n### Duplicados\n")
    dup_totales = int(df.duplicated().sum())
    salida.append(f"- Filas idénticas completas: **{dup_totales:,}**")
    col_id = df.columns[0]
    dup_id = int(df.duplicated(subset=[col_id]).sum())
    salida.append(
        f"- Repeticiones de la llave `{col_id}`: **{dup_id:,}** "
        f"({df[col_id].nunique():,} valores únicos en {len(df):,} filas)"
    )


def _reporte_integridad(datos: dict[str, pd.DataFrame],
                        salida: list[str]) -> None:
    """Cuantifica la integridad referencial entre los tres activos."""
    inv, trx, fbk = datos["inventario"], datos["transacciones"], datos["feedback"]

    salida.append(f"\n{'-' * 70}\n")
    salida.append("## Integridad referencial entre sistemas\n")

    skus_catalogo = set(inv["SKU_ID"].str.strip())
    skus_vendidos = set(trx["SKU_ID"].str.strip())
    huerfanos = skus_vendidos - skus_catalogo

    mask_fantasma = ~trx["SKU_ID"].str.strip().isin(skus_catalogo)
    n_fantasma = int(mask_fantasma.sum())

    salida.append(f"- SKU únicos en el maestro de inventario: "
                  f"**{len(skus_catalogo):,}**")
    salida.append(f"- SKU únicos con ventas: **{len(skus_vendidos):,}**")
    salida.append(f"- SKU vendidos que NO existen en el maestro: "
                  f"**{len(huerfanos):,}**")
    salida.append(
        f"- Transacciones afectadas (ventas fantasma): **{n_fantasma:,}** "
        f"de {len(trx):,} (**{100 * n_fantasma / len(trx):.2f}%**)"
    )

    if huerfanos:
        ordenados = sorted(huerfanos)
        salida.append(f"- Rango de SKU huérfanos: `{ordenados[0]}` .. "
                      f"`{ordenados[-1]}`")
        catalogo_ord = sorted(skus_catalogo)
        salida.append(f"- Rango de SKU catalogados: `{catalogo_ord[0]}` .. "
                      f"`{catalogo_ord[-1]}`")
        # Diagnóstico catálogo vs fraude: si los huérfanos forman un bloque
        # contiguo POR ENCIMA del máximo catalogado, no son errores de
        # digitación (que se dispersarían dentro del rango válido).
        sobre_maximo = sum(1 for s in huerfanos if s > catalogo_ord[-1])
        salida.append(
            f"- Huérfanos por encima del SKU máximo catalogado: "
            f"**{sobre_maximo:,}/{len(huerfanos):,}** "
            f"({100 * sobre_maximo / len(huerfanos):.1f}%)"
        )

    trx_ids = set(trx["Transaccion_ID"].str.strip())
    fbk_ids = set(fbk["Transaccion_ID"].str.strip())
    fbk_sin_trx = fbk_ids - trx_ids
    mask_fbk_huerfano = ~fbk["Transaccion_ID"].str.strip().isin(trx_ids)

    salida.append(f"- Feedback que referencia transacciones inexistentes: "
                  f"**{int(mask_fbk_huerfano.sum()):,}** filas "
                  f"({len(fbk_sin_trx):,} IDs distintos)")
    cobertura = 100 * len(trx_ids & fbk_ids) / len(trx_ids)
    salida.append(f"- Cobertura de feedback sobre ventas: **{cobertura:.2f}%** "
                  f"de las transacciones tiene al menos una opinión")


def _reporte_temporal(datos: dict[str, pd.DataFrame],
                      salida: list[str]) -> None:
    """Valida rangos de fecha y detecta registros posteriores al corte."""
    salida.append(f"\n{'-' * 70}\n")
    salida.append("## Validación temporal\n")
    salida.append(f"Evaluado contra la fecha del sistema: "
                  f"**{config.fecha_corte()}**\n")

    fechas_trx = pd.to_datetime(
        datos["transacciones"]["Fecha_Venta"],
        format=config.FORMATO_FECHA_TRANSACCIONES,
        errors="coerce",
    )
    fechas_inv = pd.to_datetime(
        datos["inventario"]["Ultima_Revision"],
        format=config.FORMATO_FECHA_INVENTARIO,
        errors="coerce",
    )
    corte = pd.Timestamp(config.fecha_corte())

    for etiqueta, serie in (("Fecha_Venta", fechas_trx),
                            ("Ultima_Revision", fechas_inv)):
        futuras = int((serie > corte).sum())
        salida.append(
            f"- **{etiqueta}**: rango {serie.min():%Y-%m-%d} .. "
            f"{serie.max():%Y-%m-%d} | no parseables: "
            f"**{int(serie.isna().sum()):,}** | posteriores al corte: "
            f"**{futuras:,}**"
        )

    antiguedad = (corte - fechas_inv).dt.days
    salida.append(
        f"- Antigüedad de la última revisión de stock (días): "
        f"mín {antiguedad.min():.0f}, mediana {antiguedad.median():.0f}, "
        f"máx {antiguedad.max():.0f}"
    )


def main() -> int:
    """Ejecuta el perfilado completo y persiste el reporte en docs/."""
    try:
        datos = ingest.cargar_todos_crudos()
    except ingest.ErrorIngesta as exc:
        print(f"[ERROR] Falló la ingesta: {exc}", file=sys.stderr)
        return 1

    salida = [
        "# Perfilado forense de datos crudos — TechLogistics S.A.S.",
        "",
        "Línea base **ANTES** de cualquier limpieza. Generado por "
        "`scripts/perfilado_inicial.py`.",
        "",
        "> Los datos se leen sin coerción de tipos ni interpretación de nulos, "
        "para que las métricas reflejen exactamente lo que hay en disco.",
    ]

    for nombre, df in datos.items():
        _reporte_dataset(nombre, df, salida)

    _reporte_integridad(datos, salida)
    _reporte_temporal(datos, salida)

    config.DIR_DOCS.mkdir(parents=True, exist_ok=True)
    destino = config.DIR_DOCS / "perfilado_inicial.md"
    try:
        destino.write_text("\n".join(salida), encoding="utf-8")
    except OSError as exc:
        print(f"[ERROR] No se pudo escribir el reporte: {exc}", file=sys.stderr)
        return 1

    print(SEPARADOR)
    print("\n".join(salida))
    print(SEPARADOR)
    print(f"Reporte guardado en: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
