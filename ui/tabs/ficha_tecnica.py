"""Pestaña de Ficha Técnica: catálogo de las técnicas estadísticas del proyecto.

No depende del recorte del panel lateral: es material de referencia, igual
que Auditoría y Transparencia. Cada técnica trae un ejemplo calculado **en
vivo** sobre la operación completa (o leído directamente de la bitácora de
limpieza ya calculada en la Fase 1), para que la ficha nunca quede
desincronizada del código que describe.
"""

from __future__ import annotations

import streamlit as st

from src import analytics
from src.cleaning import ResultadoLimpieza
from src.integration import ResultadoIntegracion

_RENOMBRES = {
    "que_es": "Qué es",
    "para_que_sirve": "Para qué sirve",
    "como_se_usa_aqui": "Cómo se usa en este proyecto",
    "como_interpretar": "Cómo se interpreta",
}


def _evidencia(curaduria: ResultadoLimpieza, dataset: str, columna: str,
              prefijo_accion: str) -> str:
    """Evidencia estadística de una acción ya registrada en la bitácora de
    limpieza, para no repetir aquí un cálculo que ``cleaning.py`` ya hizo."""
    for accion in curaduria.registro.acciones:
        if (accion.dataset == dataset and accion.columna == columna
                and accion.accion.startswith(prefijo_accion)):
            return accion.evidencia
    return "Sin evidencia disponible para el recorte actual."


def _construir_catalogo(curaduria: ResultadoLimpieza,
                        integrado: ResultadoIntegracion) -> list[dict]:
    """Catálogo de técnicas con un ejemplo real calculado en vivo por cada una."""
    ssot = integrado.ssot
    q1 = analytics.analizar_fuga_capital(ssot)
    q2 = analytics.analizar_crisis_logistica(ssot)
    q4 = analytics.analizar_paradoja_fidelidad(ssot)
    politica = integrado.politica_precios
    fantasma = integrado.diagnostico_fantasma
    criterio_precio = fantasma.get("criterios", {}).get("precio", {})

    return [
        # --- Inferencia estadística (Fase 3: las cinco preguntas) --------
        {
            "nombre": "Valor p",
            "grupo": "Inferencia estadística",
            "que_es": (
                "La probabilidad de observar un resultado al menos tan "
                "extremo como el obtenido, **si la hipótesis nula fuera "
                "cierta** (si en realidad no hubiera efecto, diferencia o "
                "relación alguna)."),
            "para_que_sirve": (
                "Decidir si un patrón observado es distinguible del azar, "
                "antes de gastar un minuto interpretándolo."),
            "como_se_usa_aqui": (
                "Es el primer filtro de todo `Veredicto` en "
                "`src/analytics.py` (propiedad `significativo`), comparado "
                "contra α = 0,05 (`config.ALFA_SIGNIFICANCIA`)."),
            "como_interpretar": (
                "p < 0,05 → 'significativo', distinguible de cero. **Pero "
                "el proyecto nunca se detiene ahí**: con 8.000 a 10.000 "
                "filas el p-valor se vuelve trivialmente pequeño ante "
                "cualquier diferencia mínima. Por eso todo hallazgo exige "
                "además un tamaño de efecto no trivial (propiedad "
                "`concluyente`) antes de sostener una recomendación."),
            "ejemplo": (
                f"Pregunta 1, canal de venta: p = "
                f"{q1.veredicto_canal.p_valor:.4f} (significativo) pero V "
                f"de Cramér = {q1.veredicto_canal.tamano_efecto:.4f} "
                f"(trivial) → etiqueta '{q1.veredicto_canal.etiqueta}'. Es "
                "el ejemplo central del proyecto de por qué el p-valor "
                "solo no basta."),
        },
        {
            "nombre": "Chi-cuadrado de independencia",
            "grupo": "Inferencia estadística",
            "que_es": (
                "Prueba no paramétrica que compara las frecuencias "
                "observadas en una tabla de contingencia (dos variables "
                "categóricas) contra las que se esperarían si fueran "
                "independientes."),
            "para_que_sirve": (
                "Responder '¿la distribución de una variable categórica "
                "cambia según el valor de otra?' — p. ej., ¿la tasa de "
                "margen negativo depende del canal de venta?"),
            "como_se_usa_aqui": (
                "`probar_independencia()`, con `scipy.stats."
                "chi2_contingency`. Pregunta 1 (margen negativo vs. canal) "
                "y pregunta 4 (causa de la queja vs. categoría)."),
            "como_interpretar": (
                "El estadístico χ² crece con el tamaño de la muestra y "
                "**no es comparable entre análisis distintos**: siempre se "
                "lee junto a la V de Cramér, nunca solo."),
            "ejemplo": (
                f"Pregunta 1: χ² = {q1.veredicto_canal.estadistico:.2f}, "
                f"p = {q1.veredicto_canal.p_valor:.4f}, "
                f"n = {q1.veredicto_canal.n:,}."),
        },
        {
            "nombre": "V de Cramér",
            "grupo": "Inferencia estadística",
            "que_es": (
                "Normalización del chi-cuadrado a una escala de 0 a 1, "
                "independiente del tamaño de la muestra."),
            "para_que_sirve": (
                "Medir **cuánto importa** una asociación categórica, no "
                "solo si existe: el tamaño de efecto que acompaña al "
                "chi-cuadrado."),
            "como_se_usa_aqui": "`_v_de_cramer()`, junto a cada chi-cuadrado.",
            "como_interpretar": (
                "Umbrales convencionales de Cohen (los mismos que usa el "
                "proyecto para épsilon cuadrado y ρ de Spearman): "
                "< 0,10 trivial · 0,10-0,30 pequeño · 0,30-0,50 medio · "
                "> 0,50 grande."),
            "ejemplo": (
                f"Pregunta 1, canal de venta: V de Cramér = "
                f"{q1.veredicto_canal.tamano_efecto:.4f} → magnitud "
                f"'{q1.veredicto_canal.magnitud}'. Con V = 0,04 la "
                "diferencia entre canales no sostiene ninguna "
                "recomendación, aunque el p-valor sea significativo."),
        },
        {
            "nombre": "Correlación de Spearman (ρ)",
            "grupo": "Inferencia estadística",
            "que_es": (
                "Correlación calculada sobre los **rangos** de los datos, "
                "no sobre sus valores crudos. Mide relación monótona (no "
                "necesariamente lineal) entre dos variables."),
            "para_que_sirve": (
                "Se prefiere sobre la correlación de Pearson porque no "
                "asume normalidad ni linealidad, y es robusta a los "
                "valores extremos, abundantes en estos datos."),
            "como_se_usa_aqui": (
                "`probar_correlacion()` y `correlaciones_por_grupo()` "
                "(pregunta 2: tiempo de entrega vs. NPS, por ciudad y "
                "bodega) y `diagnosticar_politica_precios()` "
                "(pregunta 1: costo vs. precio de venta)."),
            "como_interpretar": (
                "Rango -1 a 1; 0 = sin relación monótona. A diferencia del "
                "chi-cuadrado, ρ ya es su propio tamaño de efecto: no hace "
                "falta una fórmula aparte."),
            "ejemplo": (
                f"Política de precios (pregunta 1): ρ = "
                f"{politica.get('spearman_rho', float('nan')):.4f}, "
                f"p = {politica.get('p_valor', float('nan')):.4f} sobre "
                f"{politica.get('n', 0):,} transacciones catalogadas. "
                f"{politica.get('veredicto', '')}"),
        },
        {
            "nombre": "Corrección de Bonferroni",
            "grupo": "Inferencia estadística",
            "que_es": (
                "Ajuste que multiplica cada p-valor por el número de "
                "comparaciones realizadas en el mismo análisis."),
            "para_que_sirve": (
                "Evitar falsos positivos al repetir una misma prueba "
                "muchas veces: evaluar 5 ciudades × 5 bodegas a α = 0,05 "
                "da ~23 % de probabilidad de que al menos una dé "
                "'significativa' por puro azar."),
            "como_se_usa_aqui": (
                "`correlaciones_por_grupo()`, pregunta 2: "
                "`p_corregido = p_crudo × n_comparaciones` (acotado a "
                "1,0)."),
            "como_interpretar": (
                "Es conservadora a propósito: reduce falsos positivos a "
                "costa de poder estadístico. Apropiada cuando la decisión "
                "que respalda —cambiar de operador logístico— es cara y "
                "difícil de revertir."),
            "ejemplo": (
                f"Pregunta 2: {q2.kpis.get('correlaciones_significativas', 0)} "
                f"de {q2.kpis.get('correlaciones_evaluadas', 0)} "
                "correlaciones ciudad/bodega sobreviven a la corrección. "
                "Ninguna plaza queda señalada como la culpable del cuello "
                "de botella."),
        },
        {
            "nombre": "Kruskal-Wallis",
            "grupo": "Inferencia estadística",
            "que_es": (
                "Equivalente no paramétrico del ANOVA de un factor: "
                "compara si la distribución (por rangos) de una variable "
                "difiere entre 3 o más grupos."),
            "para_que_sirve": (
                "Comparar medianas entre categorías sin asumir "
                "normalidad — apropiado para una escala ordinal como "
                "`Rating_Producto` (1 a 5), que no es una magnitud "
                "continua."),
            "como_se_usa_aqui": (
                "`_probar_diferencia_medianas()`. Pregunta 4 (calificación "
                "y stock por categoría) y pregunta 5 (antigüedad de "
                "revisión y tasa de tickets por bodega)."),
            "como_interpretar": (
                "Se acompaña siempre de épsilon cuadrado como tamaño de "
                "efecto; el estadístico H por sí solo no dice cuánto "
                "importa la diferencia."),
            "ejemplo": (
                f"Pregunta 4, calificación por categoría: H = "
                f"{q4.veredicto_sentimiento.estadistico:.2f}, "
                f"p = {q4.veredicto_sentimiento.p_valor:.4f}, "
                f"n = {q4.veredicto_sentimiento.n:,}."),
        },
        {
            "nombre": "Épsilon cuadrado (ε²)",
            "grupo": "Inferencia estadística",
            "que_es": (
                "Tamaño de efecto de Kruskal-Wallis, análogo a eta "
                "cuadrado (η²) del ANOVA: estima la proporción de la "
                "variación en los rangos que explica la pertenencia a un "
                "grupo."),
            "para_que_sirve": "Lo mismo que la V de Cramér, pero para Kruskal-Wallis.",
            "como_se_usa_aqui": (
                "`epsilon2 = (H − k + 1) / (n − k)`, donde H es el "
                "estadístico de Kruskal-Wallis, k el número de grupos y n "
                "el total de observaciones."),
            "como_interpretar": (
                "Escala 0 a 1, mismos umbrales de Cohen que la V de "
                "Cramér."),
            "ejemplo": (
                f"Pregunta 4, calificación por categoría: ε² = "
                f"{q4.veredicto_sentimiento.efecto_texto()} → magnitud "
                f"'{q4.veredicto_sentimiento.magnitud}'."),
        },
        {
            "nombre": "Kolmogorov-Smirnov (dos muestras)",
            "grupo": "Inferencia estadística",
            "que_es": (
                "Compara las funciones de distribución acumulada de dos "
                "muestras, sin asumir ninguna distribución particular para "
                "ninguna de las dos."),
            "para_que_sirve": (
                "Decidir si dos grupos provienen de la misma distribución "
                "— más riguroso que comparar solo sus medias."),
            "como_se_usa_aqui": (
                "`_criterio_precio()` en `integration.py`, uno de los seis "
                "criterios del diagnóstico de venta fantasma (pregunta 3): "
                "compara el precio de venta de los SKU huérfanos contra "
                "los catalogados."),
            "como_interpretar": (
                "p alto → no hay evidencia de que provengan de "
                "poblaciones distintas (coherente con falla de catálogo). "
                "p bajo → las distribuciones difieren (apuntaría a error "
                "de digitación o precios inventados)."),
            "ejemplo": criterio_precio.get(
                "prueba", "Sin SKU huérfanos para evaluar en este recorte."),
        },
        # --- Calidad de datos (Fase 1: limpieza) --------------------------
        {
            "nombre": "Regla de Bulmer (asimetría)",
            "grupo": "Calidad de datos (Fase 1)",
            "que_es": (
                "Estadístico de asimetría (*skewness*) de una "
                "distribución. La regla práctica de Bulmer la clasifica "
                "como aproximadamente simétrica cuando |asimetría| < 0,5."),
            "para_que_sirve": (
                "Decidir automáticamente si imputar los nulos de una "
                "columna numérica con la media o con la mediana, en vez de "
                "asumirlo a mano."),
            "como_se_usa_aqui": (
                "`_elegir_estrategia()` en `cleaning.py`, para toda "
                "columna numérica imputada: `Stock_Actual`, "
                "`Lead_Time_Dias`, `Tiempo_Entrega_Real`, `Costo_Envio`, "
                "`Edad_Cliente`."),
            "como_interpretar": (
                "Simétrica → la media y la mediana coinciden y la media es "
                "el estimador más eficiente. Sesgada → la media se "
                "desplaza hacia la cola y la mediana es robusta a ella."),
            "ejemplo": (
                f"Stock_Actual (media): "
                f"{_evidencia(curaduria, 'inventario', 'Stock_Actual', 'Imputación por')} "
                f"— Lead_Time_Dias (mediana): "
                f"{_evidencia(curaduria, 'inventario', 'Lead_Time_Dias', 'Imputación por')}"),
        },
        {
            "nombre": "Filtro de Tukey (rango intercuartílico)",
            "grupo": "Calidad de datos (Fase 1)",
            "que_es": (
                "Método clásico de detección de outliers: un valor es "
                "atípico si cae fuera de [Q1 − k·IQR, Q3 + k·IQR], con "
                "k = 1,5 (el valor clásico de Tukey)."),
            "para_que_sirve": (
                "Detectar valores atípicos sin asumir una distribución "
                "normal."),
            "como_se_usa_aqui": (
                "`detectar_outliers_iqr()` en `audit.py`, aplicado a "
                "`Costo_Unitario_USD` (inventario) y a "
                "`Precio_Venta_Final`, `Costo_Envio`, "
                "`Tiempo_Entrega_Real` (transacciones)."),
            "como_interpretar": (
                "Por sí solo puede fallar: si los datos son muy "
                "asimétricos la valla inferior puede dar negativa y no "
                "detectar outliers bajos. Por eso `Costo_Unitario_USD` se "
                "combina con un piso de negocio de USD 1."),
            "ejemplo": _evidencia(curaduria, "inventario",
                                  "Costo_Unitario_USD",
                                  "Exclusión del cálculo"),
        },
        {
            "nombre": "Entropía de Shannon normalizada",
            "grupo": "Calidad de datos (Fase 1)",
            "que_es": (
                "Mide qué tan uniforme (impredecible) es una distribución "
                "categórica: 0 = un solo valor domina por completo, 1 = "
                "todos los valores son igual de frecuentes."),
            "para_que_sirve": (
                "Decidir si imputar una nominal con su moda tiene sentido "
                "(moda claramente dominante) o fabricaría señal falsa "
                "(distribución casi uniforme, ninguna moda "
                "representativa)."),
            "como_se_usa_aqui": (
                "`_entropia_normalizada()`, umbral 0,95. `Categoria` "
                "(inventario) y `Estado_Envio` (transacciones): ambas "
                "quedan **sin imputar** por esta razón."),
            "como_interpretar": (
                "Por encima del umbral, ninguna moda es representativa: "
                "imputar inyectaría masa artificial en una sola "
                "categoría."),
            "ejemplo": _evidencia(curaduria, "inventario", "Categoria",
                                  "NO imputar"),
        },
        {
            "nombre": "Curtosis",
            "grupo": "Calidad de datos (Fase 1)",
            "que_es": (
                "Mide qué tan pesadas son las colas de una distribución "
                "respecto a la normal."),
            "para_que_sirve": (
                "Aquí no se usa como prueba de hipótesis formal, sino "
                "como **evidencia** de que un valor centinela (999 días, "
                "195 años) es un artefacto inyectado y no una cola real: "
                "al retirarlo, la curtosis colapsa de un valor extremo al "
                "de una distribución uniforme."),
            "como_se_usa_aqui": (
                "`cleaning.py`, en la detección de `Tiempo_Entrega_Real` "
                "= 999 y `Edad_Cliente` fuera del rango plausible."),
            "como_interpretar": (
                "Una caída abrupta de la curtosis al retirar un puñado de "
                "valores es evidencia de que esos valores no pertenecían "
                "a la distribución real."),
            "ejemplo": _evidencia(curaduria, "transacciones",
                                  "Tiempo_Entrega_Real",
                                  "Reclasificación de centinela"),
        },
    ]


def renderizar(curaduria: ResultadoLimpieza,
               integrado: ResultadoIntegracion) -> None:
    """Dibuja la pestaña completa de Ficha Técnica.

    Args:
        curaduria: Salida del pipeline de limpieza de la Fase 1 (para leer
            la evidencia ya calculada en la bitácora).
        integrado: Salida de la integración de la Fase 2 (para calcular los
            ejemplos en vivo sobre la operación completa).
    """
    st.header("Ficha técnica")
    st.markdown(
        "Catálogo de las técnicas estadísticas usadas en el proyecto: para "
        "qué sirven, cómo se aplican aquí y cómo se interpretan. Cada "
        "técnica trae un ejemplo **calculado en vivo** sobre la operación "
        "completa, para que nunca quede desincronizado del código que "
        "describe."
    )
    st.caption(
        "**Alcance:** igual que Auditoría y Transparencia, esta pestaña "
        "ignora los filtros del panel lateral: es material de referencia, "
        "no un análisis del recorte que el usuario tenga aplicado."
    )

    catalogo = _construir_catalogo(curaduria, integrado)
    grupos = ["(todas)"] + sorted({t["grupo"] for t in catalogo})
    elegido = st.selectbox("Filtrar por grupo", grupos,
                           key="ficha_tecnica_grupo")

    for tecnica in catalogo:
        if elegido != "(todas)" and tecnica["grupo"] != elegido:
            continue
        with st.expander(f"{tecnica['nombre']} · {tecnica['grupo']}"):
            for campo, etiqueta in _RENOMBRES.items():
                st.markdown(f"**{etiqueta}**  \n{tecnica[campo]}")
            st.info(f"**Ejemplo real en este proyecto:** {tecnica['ejemplo']}")
