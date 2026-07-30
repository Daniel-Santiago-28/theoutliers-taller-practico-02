"""Configuración central del DSS de TechLogistics S.A.S.

Este módulo es la única fuente de verdad para rutas, esquemas esperados,
mapas de normalización, umbrales de validación y parámetros del Health Score.

Toda decisión de curaduría queda declarada aquí (y no dispersa en el código)
para que el informe de hallazgos y la pestaña de Transparencia del dashboard
puedan citarla sin riesgo de desincronización.
"""

from datetime import date, datetime
from pathlib import Path

# --------------------------------------------------------------------------
# Rutas del proyecto
# --------------------------------------------------------------------------

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ_PROYECTO / "data"
DIR_CRUDO = DIR_DATOS / "raw"
DIR_PROCESADO = DIR_DATOS / "processed"
DIR_DOCS = RAIZ_PROYECTO / "docs"

ARCHIVO_INVENTARIO = DIR_CRUDO / "inventario_central_v2.csv"
ARCHIVO_TRANSACCIONES = DIR_CRUDO / "transacciones_logistica_v2.csv"
ARCHIVO_FEEDBACK = DIR_CRUDO / "feedback_clientes_v2.csv"

# --------------------------------------------------------------------------
# Temporalidad
# --------------------------------------------------------------------------


def fecha_corte() -> date:
    """Fecha de referencia para la validación temporal.

    Es la fecha de ejecución del análisis, conforme al criterio de la Guía de
    Validación ("validación temporal contra ``datetime.now()``") y a la
    indicación expresa del docente de no anclar el proyecto a enero de 2026.

    Se expone como función y no como constante de módulo a propósito: una
    constante quedaría congelada en el instante del ``import``, de modo que un
    servidor de larga vida seguiría comparando contra el día en que arrancó.
    Evaluar en cada llamada es lo que hace que la comparación sea realmente
    contra "ahora".

    Consecuencia asumida: el análisis deja de ser determinista en el tiempo.
    Un registro clasificado hoy como vigente puede seguir siéndolo mañana,
    pero el conjunto de "fechas futuras" solo puede encogerse conforme avanza
    el calendario. Los conteos temporales del informe deben citarse siempre
    junto a la fecha en que se generaron.
    """
    return datetime.now().date()


# Formatos detectados en el perfilado: los dos archivos con fechas usan
# convenciones distintas entre sí. Esta discrepancia es en sí un hallazgo
# de integración y se reporta en la auditoría.
FORMATO_FECHA_TRANSACCIONES = "%d/%m/%Y"  # 10.000/10.000 filas
FORMATO_FECHA_INVENTARIO = "%Y-%m-%d"     # 2.500/2.500 filas

# --------------------------------------------------------------------------
# Esquemas esperados (contrato de ingesta)
# --------------------------------------------------------------------------

COLUMNAS_INVENTARIO = [
    "SKU_ID",
    "Categoria",
    "Stock_Actual",
    "Costo_Unitario_USD",
    "Punto_Reorden",
    "Lead_Time_Dias",
    "Bodega_Origen",
    "Ultima_Revision",
]

COLUMNAS_TRANSACCIONES = [
    "Transaccion_ID",
    "SKU_ID",
    "Fecha_Venta",
    "Cantidad_Vendida",
    "Precio_Venta_Final",
    "Costo_Envio",
    "Tiempo_Entrega_Real",
    "Estado_Envio",
    "Ciudad_Destino",
    "Canal_Venta",
]

COLUMNAS_FEEDBACK = [
    "Feedback_ID",
    "Transaccion_ID",
    "Rating_Producto",
    "Rating_Logistica",
    "Comentario_Texto",
    "Recomienda_Marca",
    "Ticket_Soporte_Abierto",
    "Edad_Cliente",
    "Satisfaccion_NPS",
]

ESQUEMAS = {
    "inventario": COLUMNAS_INVENTARIO,
    "transacciones": COLUMNAS_TRANSACCIONES,
    "feedback": COLUMNAS_FEEDBACK,
}

# --------------------------------------------------------------------------
# Centinelas de nulos codificados como texto
# --------------------------------------------------------------------------

# Estos valores no son datos: son ausencias disfrazadas de string. Se pasan a
# read_csv como na_values para que el conteo de nulidad de la auditoría
# refleje la ausencia real y no un falso 0 %.
CENTINELAS_NULOS = ["???", "N/A", "n/a", "NA", "---", "-", "nan", "NaN", "None", ""]

# --------------------------------------------------------------------------
# Mapas de normalización categórica
# --------------------------------------------------------------------------

# Criterio de aceptación de la guía de validación: al filtrar en el sidebar
# debe aparecer una única opción coherente por entidad del mundo real.

MAPA_CATEGORIAS = {
    "smart-phone": "Smartphones",
    "smartphone": "Smartphones",
    "smartphones": "Smartphones",
    "laptop": "Laptops",
    "laptops": "Laptops",
    "monitores": "Monitores",
    "monitor": "Monitores",
    "tablets": "Tablets",
    "tablet": "Tablets",
    "accesorios": "Accesorios",
    "accesorio": "Accesorios",
}

MAPA_BODEGAS = {
    "norte": "Norte",
    "sur": "Sur",
    "occidente": "Occidente",
    "zona_franca": "Zona_Franca",
    "bod-ext-99": "BOD-EXT-99",
}

# Bodegas sin nomenclatura regional estándar. No se eliminan: son justamente
# las candidatas a "operar a ciegas" en la pregunta 5 de riesgo operativo.
BODEGAS_NO_ESTANDAR = ["Zona_Franca", "BOD-EXT-99"]

MAPA_CIUDADES = {
    "med": "Medellín",
    "medellin": "Medellín",
    "medellín": "Medellín",
    "bog": "Bogotá",
    "bogota": "Bogotá",
    "bogotá": "Bogotá",
    "cali": "Cali",
    "baq": "Barranquilla",
    "barranquilla": "Barranquilla",
    "buc": "Bucaramanga",
    "bucaramanga": "Bucaramanga",
}

# Decisión: "Ventas_Web" aparece en Ciudad_Destino pero es un canal, no un
# lugar. Se anula la geografía y se marca con bandera en vez de eliminar la
# fila: así el ingreso sigue siendo trazable al archivo original (criterio de
# aceptación de la guía) y el volumen sin geolocalización se vuelve un
# hallazgo de auditoría por derecho propio.
VALORES_CIUDAD_NO_GEOGRAFICOS = ["ventas_web", "ventas web", "web"]
COL_FLAG_SIN_GEO = "Venta_Sin_Geolocalizacion"

MAPA_BOOLEANOS = {
    "sí": True, "si": True, "s": True, "1": True, "true": True, "yes": True,
    "no": False, "n": False, "0": False, "false": False,
}

# Recomienda_Marca mezcla español, inglés y un "Maybe" que no es ni sí ni no.
# Se trata como categórica de 3 niveles, no como booleana, para no forzar
# "Maybe" hacia ninguno de los extremos.
MAPA_RECOMIENDA = {
    "si": "Sí", "sí": "Sí", "yes": "Sí",
    "no": "No",
    "maybe": "Indeciso", "tal vez": "Indeciso",
}

# Comentario_Texto es un conjunto cerrado de frases enlatadas, no texto libre.
# Se usa como proxy de sentimiento y, sobre todo, para separar la causa raíz
# en la pregunta 4: ¿la insatisfacción es por calidad o por precio?
MAPA_SENTIMIENTO = {
    "excelente": "Positivo",
    "precio justo": "Positivo",
    "lento": "Negativo",
    "dañado": "Negativo",
    "no volvería": "Negativo",
}

# Eje de causa raíz para el diagnóstico de fidelidad (pregunta 4).
MAPA_CAUSA_QUEJA = {
    "dañado": "Calidad",
    "lento": "Logística",
    "no volvería": "Precio/Valor",
    "precio justo": "Precio/Valor",
    "excelente": "Ninguna",
}

# --------------------------------------------------------------------------
# Rangos de validez (reglas de negocio)
# --------------------------------------------------------------------------

RANGO_RATING = (1, 5)          # Rating_Producto = 99 viola esta regla
RANGO_EDAD_CLIENTE = (18, 99)  # edades de 195 años son imposibles
RANGO_NPS = (-100.0, 100.0)

# Lead_Time_Dias llega como texto mezclando números, rangos y palabras.
# Decisiones de conversión, ambas documentadas para el informe:
#   - "25-30 días" -> 27.5: punto medio del intervalo, imputación estándar
#     para datos censurados por intervalo (no sesga hacia ningún extremo).
#   - "Inmediato"  -> 0.0: disponibilidad inmediata equivale a cero días de
#     espera de reposición.
MAPA_LEAD_TIME_TEXTO = {
    "25-30 días": 27.5,
    "25-30 dias": 27.5,
    "inmediato": 0.0,
}

# Umbral de "stock alto" para la paradoja de fidelidad (pregunta 4).
# Se usa percentil en vez de valor absoluto para que sea robusto a la escala.
PERCENTIL_STOCK_ALTO = 0.75

# --------------------------------------------------------------------------
# Detección de outliers
# --------------------------------------------------------------------------

# La guía de validación exige filtro por rango intercuartílico sobre costos.
# Se usa el factor clásico de Tukey. Los registros excluidos NO se borran:
# se marcan, para que el dashboard pueda ofrecer "Ver registros excluidos".
FACTOR_IQR = 1.5
COLUMNAS_OUTLIER_IQR = {
    "inventario": ["Costo_Unitario_USD"],
    "transacciones": ["Precio_Venta_Final", "Costo_Envio", "Tiempo_Entrega_Real"],
}

# Tope duro de plausibilidad logística: por encima de este valor el registro
# es un error de sistema, no un envío lento real (la guía cita 999 días).
MAX_DIAS_ENTREGA_PLAUSIBLE = 120

# --------------------------------------------------------------------------
# Integridad referencial: la "Venta Fantasma"
# --------------------------------------------------------------------------

# Decisión: left join desde transacciones. Las ventas cuyo SKU no existe en el
# maestro NO se descartan; se etiquetan y se excluyen únicamente del cálculo
# de margen (no hay costo conocido), reportándose como ingreso en riesgo.
ETIQUETA_SIN_CATALOGO = "Sin_Catalogo_Oficial"
COL_FLAG_FANTASMA = "Es_Venta_Fantasma"

# --------------------------------------------------------------------------
# Normalización del NPS
# --------------------------------------------------------------------------

# Satisfaccion_NPS llega como índice continuo -100..+100, no como la escala
# 0-10 canónica. Se conserva el valor crudo y se agrega la clasificación
# estándar, que es el lenguaje que la junta directiva reconoce y que define
# "NPS bajo" con un umbral no arbitrario para la pregunta 2.
UMBRALES_NPS = {"detractor": (-100.0, -0.001), "pasivo": (0.0, 49.999),
                "promotor": (50.0, 100.0)}
COL_SEGMENTO_NPS = "Segmento_NPS"

# --------------------------------------------------------------------------
# Significancia estadística (pregunta 2: cuello de botella logístico)
# --------------------------------------------------------------------------

# Hallazgo del perfilado inicial: Satisfaccion_NPS es ruido aleatorio. Sus
# correlaciones de Spearman con Tiempo_Entrega_Real (rho=0.002),
# Rating_Producto (-0.018) y Rating_Logistica (0.017) están todas por debajo
# de 2 errores estándar (EE ~ 0.015 con n~4450), y la variable sigue una
# Uniforme(-100, 100) casi perfecta.
#
# Decisión de presentación en dos niveles:
#   1. Se muestra el ranking de correlación por ciudad y bodega que pide el
#      enunciado, pero atenuando las celdas no significativas y declarando
#      el hallazgo nulo en un KPI destacado.
#   2. Debajo se responde el cuello de botella con las señales que sí portan
#      información: distribución de tiempos de entrega, tasa de Estado_Envio
#      adverso y tasa de tickets de soporte.
#
# Sin corrección por comparaciones múltiples, cruzar 5 ciudades x 5 bodegas
# garantiza al menos un falso positivo a alfa=0.05.
ALFA_SIGNIFICANCIA = 0.05
METODO_CORRECCION_MULTIPLE = "bonferroni"
N_MINIMO_PARA_CORRELACION = 30   # por debajo de esto no se reporta rho
ESTADOS_ENVIO_ADVERSOS = ["Perdido", "Devuelto", "Retrasado"]

# --------------------------------------------------------------------------
# Health Score
# --------------------------------------------------------------------------

# El Health Score agrega cuatro dimensiones de calidad en un índice 0-100.
# Los pesos priorizan validez y completitud: un dato presente pero fuera de
# rango engaña más que un dato ausente declarado.
PESOS_HEALTH_SCORE = {
    "completitud": 0.30,   # 1 - tasa de nulos
    "validez": 0.30,       # 1 - tasa de valores fuera de rango/regla
    "unicidad": 0.20,      # 1 - tasa de duplicados
    "consistencia": 0.20,  # 1 - tasa de categóricas no normalizadas
}

# --------------------------------------------------------------------------
# Integración con IA (Groq)
# --------------------------------------------------------------------------

# La API key NUNCA vive en el código: se lee de st.secrets o de la variable
# de entorno GROQ_API_KEY. Ver .env.example y .streamlit/secrets.toml.example.
NOMBRE_VAR_ENTORNO_GROQ = "GROQ_API_KEY"
MODELO_GROQ = "llama-3.3-70b-versatile"
TEMPERATURA_GROQ = 0.3   # bajo: se busca análisis reproducible, no creatividad
MAX_TOKENS_GROQ = 1200
TIMEOUT_GROQ_SEG = 60
